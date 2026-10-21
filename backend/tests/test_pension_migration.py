import json
import math
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.exc import IntegrityError


BACKEND_DIR = Path(__file__).resolve().parents[1]


def _cfg(db_path):
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.attributes["db_path"] = str(db_path)
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return cfg


def _engine(db_path):
    engine = create_engine(f"sqlite:///{db_path}")

    @event.listens_for(engine, "connect")
    def _foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    return engine


def _insert_contributing_data(engine, *, account=True, override=True):
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO users (id, email, name) VALUES ('user-1', 'one@example.com', 'One')"
        )
        connection.exec_driver_sql("""
            INSERT INTO salary_config
                (id, user_id, valid_from, ral, employer_contrib_rate, voluntary_contrib_rate)
            VALUES
                ('salary-1', 'user-1', '2025-01-01', 60000, 0.0200, 0.0100),
                ('salary-stop', 'user-1', '2026-07-01', 70000, 0, 0)
        """)
        if account:
            connection.exec_driver_sql("""
                INSERT INTO accounts (id, user_id, type, name, opening_balance, is_active)
                VALUES ('pension-1', 'user-1', 'pension', 'Renamed fund', 0, 1)
            """)
        if override:
            if "account_id" in {c["name"] for c in inspect(connection).get_columns("assets")}:
                connection.exec_driver_sql("""
                    INSERT INTO assets
                        (id, user_id, year, asset_type, asset_name, account_id, manual_override, notes)
                    VALUES ('asset-audit', 'user-1', 2025, 'pension', 'Legacy name', 'pension-1', 4321.50, 'statement notes')
                """)
            else:
                connection.exec_driver_sql("""
                    INSERT INTO assets
                        (id, user_id, year, asset_type, asset_name, manual_override, notes)
                    VALUES ('asset-audit', 'user-1', 2025, 'pension', 'Pension', 4321.50, 'statement notes')
                """)


@pytest.mark.parametrize("source_revision", ["012pm_link_set_null", "015account_identities", "018remove_forecasting"])
def test_pension_migration_backfills_supported_source_revisions(tmp_path, source_revision):
    db_path = tmp_path / f"source-{source_revision}.db"
    cfg = _cfg(db_path)
    command.upgrade(cfg, source_revision)
    engine = _engine(db_path)
    _insert_contributing_data(engine, account=source_revision != "012pm_link_set_null")

    command.upgrade(cfg, "head")

    with engine.connect() as connection:
        configs = connection.exec_driver_sql("""
            SELECT id, user_id, account_id, valid_from, employee_contrib_rate,
                   employee_contrib_annual_base, employer_contrib_rate,
                   employer_contrib_annual_base, tfr_contrib_annual,
                   contribution_periods_by_month
            FROM pension_configs ORDER BY valid_from
        """).mappings().all()
        assert len(configs) == 2
        assert configs[0]["valid_from"] == "2025-01-01"
        assert configs[0]["employee_contrib_rate"] == 0.01
        assert configs[0]["employee_contrib_annual_base"] == 60000
        assert configs[0]["employer_contrib_rate"] == 0.02
        assert configs[0]["employer_contrib_annual_base"] == 60000
        assert configs[0]["tfr_contrib_annual"] == 0
        assert json.loads(configs[0]["contribution_periods_by_month"]) == [1] * 12
        assert configs[1]["valid_from"] == "2026-07-01"
        assert configs[1]["employee_contrib_rate"] == 0
        assert configs[0]["account_id"] == configs[1]["account_id"]

        account = connection.exec_driver_sql("""
            SELECT id, user_id, type, opening_balance, opening_balance_month
            FROM accounts WHERE type = 'pension' AND user_id = 'user-1'
        """).mappings().one()
        assert account["user_id"] == "user-1"
        assert account["opening_balance_month"] == "2025-01-01"
        assert connection.exec_driver_sql("""
            SELECT id, user_id, account_id, as_of_month, balance, source, notes
            FROM pension_balance_snapshots
        """).mappings().one() == {
            "id": "asset-audit", "user_id": "user-1", "account_id": account["id"],
            "as_of_month": "2025-12-01", "balance": 4321.5,
            "source": "legacy_override", "notes": "statement notes",
        }
        assert connection.exec_driver_sql(
            "SELECT manual_override FROM assets WHERE id = 'asset-audit'"
        ).scalar_one() == 4321.5
        assert connection.exec_driver_sql("PRAGMA integrity_check").scalar_one() == "ok"
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    engine.dispose()


def test_migration_canonicalizes_one_ulp_legacy_float_only_in_new_config(tmp_path):
    db_path = tmp_path / "one-ulp-rate.db"
    cfg = _cfg(db_path)
    command.upgrade(cfg, "018remove_forecasting")
    engine = _engine(db_path)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO users (id, email, name) VALUES ('user-1', 'one@example.com', 'One')"
        )
        connection.exec_driver_sql("""
            INSERT INTO accounts (id, user_id, type, name, opening_balance, is_active)
            VALUES ('pension-1', 'user-1', 'pension', 'Fund', 0, 1)
        """)
        connection.exec_driver_sql("""
            INSERT INTO salary_config
                (id, user_id, valid_from, ral, employer_contrib_rate, voluntary_contrib_rate)
            VALUES ('salary-1', 'user-1', '2025-01-01', 60000, ?, 0.0100)
        """, (math.nextafter(0.04, 0.0),))
        legacy_before = connection.exec_driver_sql("""
            SELECT employer_contrib_rate, typeof(employer_contrib_rate)
            FROM salary_config WHERE id = 'salary-1'
        """).one()

    # Pin this source-preservation assertion to 019; 020 intentionally drops legacy columns.
    command.upgrade(cfg, "019pension_foundation")

    with engine.connect() as connection:
        assert connection.exec_driver_sql("""
            SELECT employer_contrib_rate FROM pension_configs
        """).scalar_one() == 0.04
        legacy_after = connection.exec_driver_sql("""
            SELECT employer_contrib_rate, typeof(employer_contrib_rate)
            FROM salary_config WHERE id = 'salary-1'
        """).one()
        assert legacy_after == legacy_before
    engine.dispose()


def test_migration_canonicalizes_adjacent_float_neighbors_at_rate_boundaries(tmp_path):
    db_path = tmp_path / "adjacent-rate-neighbors.db"
    cfg = _cfg(db_path)
    command.upgrade(cfg, "018remove_forecasting")
    engine = _engine(db_path)
    canonical_rates = [0.01, 0.04, 0.5]
    cases = []
    for canonical in canonical_rates:
        for direction in (-math.inf, math.inf):
            cases.append((canonical, math.nextafter(canonical, direction)))
    cases.extend([
        (0.0, math.nextafter(0.0, math.inf)),
        (1.0, math.nextafter(1.0, -math.inf)),
    ])
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO users (id, email, name) VALUES ('user-1', 'one@example.com', 'One')"
        )
        connection.exec_driver_sql("""
            INSERT INTO accounts (id, user_id, type, name, opening_balance, is_active)
            VALUES ('pension-1', 'user-1', 'pension', 'Fund', 0, 1)
        """)
        for index, (_, value) in enumerate(cases):
            connection.exec_driver_sql("""
                INSERT INTO salary_config
                    (id, user_id, valid_from, ral, employer_contrib_rate, voluntary_contrib_rate)
                VALUES (?, 'user-1', ?, 60000, 0, ?)
            """, (f"salary-{index}", f"2020-{index + 1:02d}-01", value))
        before = connection.exec_driver_sql("""
            SELECT id, voluntary_contrib_rate, typeof(voluntary_contrib_rate)
            FROM salary_config ORDER BY id
        """).all()

    # Pin legacy source-column preservation to 019; 020 removes these columns.
    command.upgrade(cfg, "019pension_foundation")

    with engine.connect() as connection:
        configs = connection.exec_driver_sql("""
            SELECT valid_from, employee_contrib_rate FROM pension_configs ORDER BY valid_from
        """).all()
        assert [Decimal(str(rate)) for _, rate in configs] == [Decimal(f"{canonical:.4f}") for canonical, _ in cases]
        after = connection.exec_driver_sql("""
            SELECT id, voluntary_contrib_rate, typeof(voluntary_contrib_rate)
            FROM salary_config ORDER BY id
        """).all()
        assert after == before
    engine.dispose()


def test_migration_preflight_coalesces_identical_duplicate_effective_periods(tmp_path):
    db_path = tmp_path / "identical-duplicates.db"
    cfg = _cfg(db_path)
    command.upgrade(cfg, "018remove_forecasting")
    engine = _engine(db_path)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO users (id, email, name) VALUES ('user-1', 'one@example.com', 'One')"
        )
        connection.exec_driver_sql("""
            INSERT INTO accounts (id, user_id, type, name, opening_balance, is_active)
            VALUES ('pension-1', 'user-1', 'pension', 'Fund', 0, 1)
        """)
        connection.exec_driver_sql("""
            INSERT INTO salary_config
                (id, user_id, valid_from, ral, employer_contrib_rate, voluntary_contrib_rate)
            VALUES
                ('salary-b', 'user-1', '2025-01-01', 60000, 0.02, 0.01),
                ('salary-a', 'user-1', '2025-01-01', 60000, 0.02, 0.01)
        """)
    command.upgrade(cfg, "head")
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM pension_configs").scalar_one() == 1
        assert connection.exec_driver_sql("SELECT id FROM pension_configs").scalar_one() == "salary-a"
    engine.dispose()


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("conflicting_duplicate", "conflicting salary rows"),
        ("invalid_date", "noncanonical valid_from"),
        ("invalid_rate", "outside allowed range"),
        ("negative_rate", "outside allowed range"),
        ("nonfinite_rate", "unrepresentable"),
        ("fifth_decimal_rate", "unrepresentable"),
        ("multi_ulp_rate", "unrepresentable"),
        ("invalid_ral", "outside allowed range"),
        ("invalid_ral_precision", "unrepresentable"),
        ("nonzero_opening", "nonzero undated opening balance"),
        ("foreign_override", "unmatched or foreign-owned account"),
        ("unmatched_override", "has no owned pension account"),
    ],
)
def test_migration_preflight_rejects_invalid_data_before_schema_mutation(tmp_path, case, message):
    db_path = tmp_path / f"invalid-{case}.db"
    cfg = _cfg(db_path)
    command.upgrade(cfg, "018remove_forecasting")
    engine = _engine(db_path)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO users (id, email, name) VALUES ('user-1', 'one@example.com', 'One')"
        )
        if case != "unmatched_override":
            connection.exec_driver_sql("""
                INSERT INTO accounts (id, user_id, type, name, opening_balance, is_active)
                VALUES ('pension-1', 'user-1', 'pension', 'Fund', 0, 1)
            """)
        if case == "nonzero_opening":
            connection.exec_driver_sql("UPDATE accounts SET opening_balance = 12.34 WHERE id = 'pension-1'")
        salary_date, employee_rate, ral = "2025-01-01", 0.01, 60000
        if case == "invalid_date":
            salary_date = "2025-02-15"
        if case == "invalid_rate":
            employee_rate = 1.5
        if case == "negative_rate":
            employee_rate = -0.01
        if case == "nonfinite_rate":
            employee_rate = "inf"
        if case == "fifth_decimal_rate":
            employee_rate = 0.04001
        if case == "multi_ulp_rate":
            employee_rate = math.nextafter(math.nextafter(0.04, 0.0), 0.0)
        if case == "invalid_ral":
            ral = -1
        if case == "invalid_ral_precision":
            ral = 60000.001
        connection.exec_driver_sql("""
            INSERT INTO salary_config
                (id, user_id, valid_from, ral, employer_contrib_rate, voluntary_contrib_rate)
            VALUES ('salary-1', 'user-1', ?, ?, 0, ?)
        """, (salary_date, ral, employee_rate))
        if case == "conflicting_duplicate":
            connection.exec_driver_sql("""
                INSERT INTO salary_config
                    (id, user_id, valid_from, ral, employer_contrib_rate, voluntary_contrib_rate)
                VALUES ('salary-2', 'user-1', '2025-01-01', 70000, 0, 0.01)
            """)
        if case in {"foreign_override", "unmatched_override"}:
            if case == "foreign_override":
                connection.exec_driver_sql(
                    "INSERT INTO users (id, email, name) VALUES ('user-2', 'two@example.com', 'Two')"
                )
                connection.exec_driver_sql("""
                    INSERT INTO accounts (id, user_id, type, name, opening_balance, is_active)
                    VALUES ('foreign-pension', 'user-2', 'pension', 'Foreign', 0, 1)
                """)
                account_id = "foreign-pension"
            else:
                account_id = None
            connection.exec_driver_sql("""
                INSERT INTO assets (id, user_id, year, asset_type, asset_name, account_id, manual_override)
                VALUES ('override-1', 'user-1', 2025, 'pension', 'Legacy', ?, 100.00)
            """, (account_id,))

    with pytest.raises(RuntimeError, match=message):
        command.upgrade(cfg, "head")

    with engine.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one() == "018remove_forecasting"
        assert "opening_balance_month" not in {
            column["name"] for column in inspect(engine).get_columns("accounts")
        }
        assert not {"pension_configs", "pension_balance_snapshots"} & set(inspect(engine).get_table_names())
        if case in {"foreign_override", "unmatched_override"}:
            row = connection.exec_driver_sql("""
                SELECT account_id, manual_override FROM assets WHERE id = 'override-1'
            """).mappings().one()
            assert row == {"account_id": account_id, "manual_override": 100}
    engine.dispose()


def test_migrated_snapshot_unique_constraint_rejects_duplicate_month_key(tmp_path):
    db_path = tmp_path / "migrated-snapshot-unique.db"
    cfg = _cfg(db_path)
    command.upgrade(cfg, "018remove_forecasting")
    engine = _engine(db_path)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO users (id, email, name) VALUES ('user-1', 'one@example.com', 'One')"
        )
        connection.exec_driver_sql("""
            INSERT INTO accounts (id, user_id, type, name, opening_balance, is_active)
            VALUES ('pension-1', 'user-1', 'pension', 'Fund', 0, 1)
        """)
        connection.exec_driver_sql("""
            INSERT INTO user_settings (user_id, key, value)
            VALUES ('user-1', 'tracking_start_date', '2025-01-01')
        """)
    command.upgrade(cfg, "head")
    with engine.begin() as connection:
        connection.exec_driver_sql("""
            INSERT INTO pension_balance_snapshots
                (id, user_id, account_id, as_of_month, balance, source)
            VALUES ('snapshot-first', 'user-1', 'pension-1', '2026-03-01', 100, 'statement')
        """)
    with pytest.raises(IntegrityError) as error:
        with engine.begin() as connection:
            connection.exec_driver_sql("""
                INSERT INTO pension_balance_snapshots
                    (id, user_id, account_id, as_of_month, balance, source)
                VALUES ('snapshot-duplicate', 'user-1', 'pension-1', '2026-03-01', 200, 'manual')
            """)
    assert "UNIQUE constraint failed: pension_balance_snapshots.user_id, pension_balance_snapshots.account_id, pension_balance_snapshots.as_of_month" in str(error.value)
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM pension_balance_snapshots").scalar_one() == 1
    engine.dispose()


def test_pension_snapshot_foreign_key_enforces_user_account_ownership_and_cascade(tmp_path):
    db_path = tmp_path / "snapshot-fks.db"
    cfg = _cfg(db_path)
    command.upgrade(cfg, "018remove_forecasting")
    engine = _engine(db_path)
    with engine.begin() as connection:
        connection.exec_driver_sql("""
            INSERT INTO users (id, email, name) VALUES
                ('user-1', 'one@example.com', 'One'), ('user-2', 'two@example.com', 'Two')
        """)
        connection.exec_driver_sql("""
            INSERT INTO accounts (id, user_id, type, name, opening_balance, is_active)
            VALUES ('pension-1', 'user-1', 'pension', 'Fund', 0, 1)
        """)
        connection.exec_driver_sql("""
            INSERT INTO user_settings (user_id, key, value)
            VALUES ('user-1', 'tracking_start_date', '2025-01-01')
        """)
    command.upgrade(cfg, "head")
    with pytest.raises(Exception):
        with engine.begin() as connection:
            connection.exec_driver_sql("""
                INSERT INTO pension_balance_snapshots
                    (id, user_id, account_id, as_of_month, balance, source)
                VALUES ('forged', 'user-2', 'pension-1', '2026-01-01', 1, 'manual')
            """)
    with engine.begin() as connection:
        connection.exec_driver_sql("DELETE FROM users WHERE id = 'user-1'")
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM pension_balance_snapshots").scalar_one() == 0
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM accounts WHERE id = 'pension-1'").scalar_one() == 0
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    engine.dispose()


def test_all_zero_history_skips_pension_config_and_account_without_changing_saving_account(tmp_path):
    db_path = tmp_path / "zero-history.db"
    cfg = _cfg(db_path)
    command.upgrade(cfg, "018remove_forecasting")
    engine = _engine(db_path)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO users (id, email, name) VALUES ('user-1', 'one@example.com', 'One')"
        )
        connection.exec_driver_sql("""
            INSERT INTO accounts (id, user_id, type, name, opening_balance, is_active)
            VALUES ('saving-1', 'user-1', 'saving', 'Savings', 500, 1)
        """)
        connection.exec_driver_sql("""
            INSERT INTO salary_config
                (id, user_id, valid_from, ral, employer_contrib_rate, voluntary_contrib_rate)
            VALUES ('salary-zero', 'user-1', '2025-01-01', 60000, 0, 0)
        """)
    command.upgrade(cfg, "head")
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM pension_configs").scalar_one() == 0
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM accounts WHERE type='pension'").scalar_one() == 0
        assert connection.exec_driver_sql("""
            SELECT opening_balance, opening_balance_month FROM accounts WHERE id='saving-1'
        """).one() == (500, None)
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    engine.dispose()


def test_multiple_legacy_pension_destinations_reject_before_ddl(tmp_path):
    db_path = tmp_path / "ambiguous-pension-destinations.db"
    cfg = _cfg(db_path)
    command.upgrade(cfg, "018remove_forecasting")
    engine = _engine(db_path)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO users (id, email, name) VALUES ('user-1', 'one@example.com', 'One')"
        )
        connection.exec_driver_sql("""
            INSERT INTO accounts (id, user_id, type, name, opening_balance, is_active)
            VALUES
                ('pension-1', 'user-1', 'pension', 'Fund A', 0, 1),
                ('pension-2', 'user-1', 'pension', 'Fund B', 0, 1)
        """)
        connection.exec_driver_sql("""
            INSERT INTO salary_config
                (id, user_id, valid_from, ral, employer_contrib_rate, voluntary_contrib_rate)
            VALUES ('salary-1', 'user-1', '2025-01-01', 60000, 0.02, 0.01)
        """)

    with pytest.raises(RuntimeError, match="multiple pension accounts"):
        command.upgrade(cfg, "head")

    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == "018remove_forecasting"
        assert connection.exec_driver_sql("SELECT id FROM accounts WHERE type='pension' ORDER BY id").scalars().all() == ["pension-1", "pension-2"]
        assert "opening_balance_month" not in {c["name"] for c in inspect(engine).get_columns("accounts")}
        assert not {"pension_configs", "pension_balance_snapshots"} & set(inspect(engine).get_table_names())
    engine.dispose()


def test_owned_transfer_before_config_sets_pension_opening_month(tmp_path):
    db_path = tmp_path / "transfer-opening-boundary.db"
    cfg = _cfg(db_path)
    command.upgrade(cfg, "018remove_forecasting")
    engine = _engine(db_path)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO users (id, email, name) VALUES ('user-1', 'one@example.com', 'One')"
        )
        connection.exec_driver_sql("""
            INSERT INTO accounts (id, user_id, type, name, opening_balance, is_active)
            VALUES ('pension-1', 'user-1', 'pension', 'Fund', 0, 1)
        """)
        connection.exec_driver_sql("""
            INSERT INTO salary_config
                (id, user_id, valid_from, ral, employer_contrib_rate, voluntary_contrib_rate)
            VALUES ('salary-1', 'user-1', '2026-07-01', 60000, 0.02, 0.01)
        """)
        connection.exec_driver_sql("""
            INSERT INTO transfers
                (id, user_id, date, detail, amount, from_account_type, from_account_name,
                 to_account_type, to_account_name, billing_month, to_account_id)
            VALUES ('transfer-early', 'user-1', '2026-03-15', 'Historical pension transfer', 10,
                    'bank', 'Bank', 'pension', 'Fund', '2026-03-01', 'pension-1')
        """)
    command.upgrade(cfg, "head")
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT opening_balance_month FROM accounts WHERE id='pension-1'").scalar_one() == "2026-03-01"
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM transfers WHERE id='transfer-early'").scalar_one() == 1
    engine.dispose()


def test_december_override_before_configuration_sets_opening_month(tmp_path):
    db_path = tmp_path / "override-opening-boundary.db"
    cfg = _cfg(db_path)
    command.upgrade(cfg, "018remove_forecasting")
    engine = _engine(db_path)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO users (id, email, name) VALUES ('user-1', 'one@example.com', 'One')"
        )
        connection.exec_driver_sql("""
            INSERT INTO accounts (id, user_id, type, name, opening_balance, is_active)
            VALUES ('pension-1', 'user-1', 'pension', 'Fund', 0, 1)
        """)
        connection.exec_driver_sql("""
            INSERT INTO salary_config
                (id, user_id, valid_from, ral, employer_contrib_rate, voluntary_contrib_rate)
            VALUES ('salary-1', 'user-1', '2025-02-01', 60000, 0.02, 0.01)
        """)
        connection.exec_driver_sql("""
            INSERT INTO assets
                (id, user_id, year, asset_type, asset_name, account_id, manual_override, notes)
            VALUES ('override-early', 'user-1', 2024, 'pension', 'Fund', 'pension-1', 100, 'audit preserved')
        """)
    command.upgrade(cfg, "head")
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT opening_balance_month FROM accounts WHERE id='pension-1'").scalar_one() == "2024-12-01"
        assert connection.exec_driver_sql("SELECT as_of_month FROM pension_balance_snapshots WHERE id='override-early'").scalar_one() == "2024-12-01"
        assert connection.exec_driver_sql("SELECT notes FROM assets WHERE id='override-early'").scalar_one() == "audit preserved"
    engine.dispose()


def test_tracking_start_fallback_used_only_without_dated_pension_history(tmp_path):
    valid_db = tmp_path / "tracking-fallback-valid.db"
    valid_cfg = _cfg(valid_db)
    command.upgrade(valid_cfg, "018remove_forecasting")
    valid_engine = _engine(valid_db)
    with valid_engine.begin() as connection:
        connection.exec_driver_sql("INSERT INTO users (id, email, name) VALUES ('user-1', 'one@example.com', 'One')")
        connection.exec_driver_sql("INSERT INTO accounts (id, user_id, type, name, opening_balance, is_active) VALUES ('pension-1', 'user-1', 'pension', 'Fund', 0, 1)")
        connection.exec_driver_sql("INSERT INTO user_settings (user_id, key, value) VALUES ('user-1', 'tracking_start_date', '2024-09-01')")
    command.upgrade(valid_cfg, "head")
    with valid_engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT opening_balance_month FROM accounts WHERE id='pension-1'").scalar_one() == "2024-09-01"
    valid_engine.dispose()

    invalid_db = tmp_path / "tracking-fallback-invalid.db"
    invalid_cfg = _cfg(invalid_db)
    command.upgrade(invalid_cfg, "018remove_forecasting")
    invalid_engine = _engine(invalid_db)
    with invalid_engine.begin() as connection:
        connection.exec_driver_sql("INSERT INTO users (id, email, name) VALUES ('user-1', 'one@example.com', 'One')")
        connection.exec_driver_sql("INSERT INTO accounts (id, user_id, type, name, opening_balance, is_active) VALUES ('pension-1', 'user-1', 'pension', 'Fund', 0, 1)")
        connection.exec_driver_sql("INSERT INTO user_settings (user_id, key, value) VALUES ('user-1', 'tracking_start_date', '2024-09-15')")
    with pytest.raises(RuntimeError, match="noncanonical tracking_start_date"):
        command.upgrade(invalid_cfg, "head")
    with invalid_engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == "018remove_forecasting"
        assert "opening_balance_month" not in {c["name"] for c in inspect(invalid_engine).get_columns("accounts")}
        assert connection.exec_driver_sql("SELECT value FROM user_settings WHERE key='tracking_start_date'").scalar_one() == "2024-09-15"
    invalid_engine.dispose()


@pytest.mark.parametrize("prefix", ["from", "to"])
@pytest.mark.parametrize("reference", ["null", "foreign", "unmatched"])
def test_pension_transfer_endpoint_requires_owned_stable_account_id(tmp_path, prefix, reference):
    db_path = tmp_path / f"transfer-ref-{prefix}-{reference}.db"
    cfg = _cfg(db_path)
    command.upgrade(cfg, "018remove_forecasting")
    engine = _engine(db_path)
    with engine.begin() as connection:
        connection.exec_driver_sql("""
            INSERT INTO users (id, email, name) VALUES
                ('user-1', 'one@example.com', 'One'), ('user-2', 'two@example.com', 'Two')
        """)
        connection.exec_driver_sql("""
            INSERT INTO accounts (id, user_id, type, name, opening_balance, is_active)
            VALUES
                ('pension-owned', 'user-1', 'pension', 'Owned', 0, 1),
                ('pension-foreign', 'user-2', 'pension', 'Foreign', 0, 1),
                ('investment-owned', 'user-1', 'investment', 'Other type', 0, 1)
        """)
        connection.exec_driver_sql("""
            INSERT INTO salary_config
                (id, user_id, valid_from, ral, employer_contrib_rate, voluntary_contrib_rate)
            VALUES ('salary-1', 'user-1', '2026-06-01', 60000, 0.02, 0.01)
        """)
        if reference == "null":
            account_id = None
        elif reference == "foreign":
            account_id = "pension-foreign"
        else:
            account_id = "investment-owned"
        from_type = "pension" if prefix == "from" else "bank"
        to_type = "pension" if prefix == "to" else "investment"
        from_id = account_id if prefix == "from" else None
        to_id = account_id if prefix == "to" else "investment-owned"
        connection.exec_driver_sql("""
            INSERT INTO transfers
                (id, user_id, date, detail, amount, from_account_type, from_account_name,
                 to_account_type, to_account_name, billing_month, from_account_id, to_account_id)
            VALUES ('transfer-bad-ref', 'user-1', '2026-01-15', 'Transfer', 10, ?, 'Fund', ?, 'Other', '2026-01-01', ?, ?)
        """, (from_type, to_type, from_id, to_id))
        transfer_before = connection.exec_driver_sql("""
            SELECT id, date, from_account_type, from_account_id, to_account_type, to_account_id
            FROM transfers WHERE id = 'transfer-bad-ref'
        """).one()

    message = "without a stable account ID" if reference == "null" else "unmatched or foreign pension account reference"
    with pytest.raises(RuntimeError, match=message):
        command.upgrade(cfg, "head")

    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == "018remove_forecasting"
        assert "opening_balance_month" not in {c["name"] for c in inspect(engine).get_columns("accounts")}
        assert not {"pension_configs", "pension_balance_snapshots"} & set(inspect(engine).get_table_names())
        assert connection.exec_driver_sql("""
            SELECT id, date, from_account_type, from_account_id, to_account_type, to_account_id
            FROM transfers WHERE id = 'transfer-bad-ref'
        """).one() == transfer_before
    engine.dispose()


def test_forced_sqlite_ddl_failure_inspects_partial_schema_and_revision(tmp_path):
    db_path = tmp_path / "ddl-failure.db"
    cfg = _cfg(db_path)
    command.upgrade(cfg, "018remove_forecasting")
    engine = _engine(db_path)
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE pension_configs (sentinel TEXT)")

    with pytest.raises(Exception, match="already exists"):
        command.upgrade(cfg, "head")

    with engine.connect() as connection:
        tables = set(inspect(engine).get_table_names())
        account_columns = {column["name"] for column in inspect(engine).get_columns("accounts")}
        assert "opening_balance_month" in account_columns
        assert "pension_configs" in tables
        assert "pension_balance_snapshots" not in tables
        assert connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one() == "018remove_forecasting"
        assert connection.exec_driver_sql("PRAGMA integrity_check").scalar_one() == "ok"
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    engine.dispose()


def test_conflicting_override_failure_is_private_and_leaves_source_unchanged(tmp_path):
    db_path = tmp_path / "conflicting-overrides.db"
    cfg = _cfg(db_path)
    command.upgrade(cfg, "018remove_forecasting")
    engine = _engine(db_path)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO users (id, email, name) VALUES ('user-1', 'one@example.com', 'One')"
        )
        connection.exec_driver_sql("""
            INSERT INTO accounts (id, user_id, type, name, opening_balance, is_active)
            VALUES ('pension-1', 'user-1', 'pension', 'Fund', 0, 1)
        """)
        connection.exec_driver_sql("""
            INSERT INTO assets
                (id, user_id, year, asset_type, asset_name, account_id, manual_override, notes)
            VALUES
                ('override-first', 'user-1', 2025, 'pension', 'Fund', 'pension-1', 123.45, 'PRIVATE_NOTE_MARKER'),
                ('override-second', 'user-1', 2025, 'pension', 'Fund', 'pension-1', 678.90, 'second note')
        """)
        original_rows = connection.exec_driver_sql("""
            SELECT id, account_id, manual_override, notes FROM assets ORDER BY id
        """).all()

    with pytest.raises(RuntimeError) as error:
        command.upgrade(cfg, "head")

    message = str(error.value)
    assert "override-first" in message and "override-second" in message
    assert "PRIVATE_NOTE_MARKER" not in message
    assert "123.45" not in message and "678.9" not in message
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == "018remove_forecasting"
        assert "opening_balance_month" not in {c["name"] for c in inspect(engine).get_columns("accounts")}
        assert not {"pension_configs", "pension_balance_snapshots"} & set(inspect(engine).get_table_names())
        assert connection.exec_driver_sql("""
            SELECT id, account_id, manual_override, notes FROM assets ORDER BY id
        """).all() == original_rows
    engine.dispose()
