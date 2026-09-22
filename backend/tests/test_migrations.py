# backend/tests/test_migrations.py
import os
import subprocess
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.services.bank_balance import compute_bank_balance


def _cfg(db_path: str) -> Config:
    """Return Alembic config pointed at a temp DB."""
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.attributes["db_path"] = db_path
    cfg.set_main_option(
        "script_location",
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "alembic")),
    )
    return cfg


def _head_revision() -> str:
    return ScriptDirectory.from_config(_cfg(":memory:")).get_current_head()


def test_direct_alembic_cli_uses_configured_db_path(tmp_path):
    """Direct Alembic CLI migrations must use DB_PATH, not the container default."""
    db_path = tmp_path / "cli-custom.db"
    backend_dir = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.update({"DB_PATH": str(db_path), "DEVELOPMENT_MODE": "true"})

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=backend_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with engine.connect() as connection:
            revision = connection.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).scalar_one()
        assert revision == _head_revision()
    finally:
        engine.dispose()


def test_migration_head_creates_expected_schema():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        command.upgrade(_cfg(db_path), "head")
        inspector = inspect(engine)

        # transfers table
        transfer_cols = {c["name"] for c in inspector.get_columns("transfers")}
        assert "parent_transfer_id" in transfer_cols

        # salary_config table
        salary_cols = {c["name"] for c in inspector.get_columns("salary_config")}
        assert "salary_months" in salary_cols

        # tax_config table — new column names, old names gone
        tax_cols = {c["name"] for c in inspector.get_columns("tax_config")}
        assert "employment_deduction_band1_limit" in tax_cols
        assert "employment_deduction_floor" in tax_cols
        assert "user_id" in tax_cols
        assert "detrazione_band1_limit" not in tax_cols

        # payment_methods — unique constraint
        unique_constraints = {
            uc["name"] for uc in inspector.get_unique_constraints("payment_methods")
        }
        assert "uq_pm_user_name" in unique_constraints
        pm_link_fks = [
            fk for fk in inspector.get_foreign_keys("payment_methods")
            if fk["referred_table"] == "payment_methods"
            and fk["constrained_columns"] == ["linked_bank_id"]
        ]
        assert len(pm_link_fks) == 1, f"Expected 1 self-FK on linked_bank_id, got: {pm_link_fks}"
        assert pm_link_fks[0]["options"].get("ondelete", "").upper() == "SET NULL", (
            f"Expected SET NULL on payment_methods.linked_bank_id, got: {pm_link_fks[0]}"
        )

        # card-bank link history — effective dates are unique per card
        link_cols = {c["name"] for c in inspector.get_columns("card_bank_link_history")}
        assert link_cols == {
            "id", "user_id", "card_payment_method_id", "linked_bank_id", "valid_from",
        }
        link_unique_constraints = {
            uc["name"] for uc in inspector.get_unique_constraints("card_bank_link_history")
        }
        assert "uq_card_bank_link_effective" in link_unique_constraints

        # Reconciled ORM non-null constraints and indexes.
        expected_not_null = {
            "forecast_adjustments": ("adjustment_type",),
            "forecasts": ("created_at", "updated_at"),
            "transactions": ("created_at", "updated_at"),
            "transfers": ("created_at",),
            "user_settings": ("updated_at",),
            "users": ("created_at",),
        }
        for table_name, column_names in expected_not_null.items():
            columns = {c["name"]: c for c in inspector.get_columns(table_name)}
            for column_name in column_names:
                assert columns[column_name]["nullable"] is False, (
                    f"{table_name}.{column_name} must be non-null"
                )

        user_indexes = {idx["name"]: idx for idx in inspector.get_indexes("users")}
        assert user_indexes["ix_users_email"]["unique"]
        assert user_indexes["ix_users_oidc_sub"]["unique"]

        # transactions — category_id FK must have exactly one reference to categories with RESTRICT
        tx_cols = {c["name"] for c in inspector.get_columns("transactions")}
        tx_cols_by_name = {c["name"]: c for c in inspector.get_columns("transactions")}
        assert "installment_total" not in tx_cols
        assert "installment_index" not in tx_cols
        tx_fks = inspector.get_foreign_keys("transactions")
        pm_fks = [fk for fk in tx_fks if fk["referred_table"] == "payment_methods"]
        assert len(pm_fks) == 1, f"Expected 1 FK to payment_methods, got {len(pm_fks)}: {pm_fks}"
        assert tx_cols_by_name["payment_method_id"]["nullable"] is True
        assert pm_fks[0]["options"].get("ondelete", "").upper() == "SET NULL", (
            f"Expected SET NULL ondelete on transactions.payment_method_id, got: {pm_fks[0]}"
        )
        cat_fks = [fk for fk in tx_fks if fk["referred_table"] == "categories"]
        assert len(cat_fks) == 1, f"Expected 1 FK to categories, got {len(cat_fks)}: {cat_fks}"
        assert cat_fks[0]["options"].get("ondelete", "").upper() == "RESTRICT", (
            f"Expected RESTRICT ondelete on transactions.category_id, got: {cat_fks[0]}"
        )

        # main_bank_history FK must have exactly one reference to payment_methods with CASCADE
        fks = inspector.get_foreign_keys("main_bank_history")
        pm_fks = [fk for fk in fks if fk["referred_table"] == "payment_methods"]
        assert len(pm_fks) == 1, f"Expected 1 FK to payment_methods, got {len(pm_fks)}: {pm_fks}"
        assert pm_fks[0]["options"]["ondelete"].upper() == "CASCADE", f"Expected CASCADE ondelete, got: {pm_fks[0]}"

        # main_bank_history — user_id index must survive the batch rebuild in 003
        mbh_index_names = {idx["name"] for idx in inspector.get_indexes("main_bank_history")}
        assert "ix_main_bank_history_user_id" in mbh_index_names, (
            f"ix_main_bank_history_user_id missing from main_bank_history. Found: {mbh_index_names}"
        )

        # A fresh migrated database must exactly match the registered ORM metadata.
        command.check(_cfg(db_path))
    finally:
        engine.dispose()
        os.unlink(db_path)


def test_migration_013_backfills_current_card_links_from_previous_head():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        cfg = _cfg(db_path)
        command.upgrade(cfg, "012pm_link_set_null")
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO users (id, email, name) VALUES ('user-1', 'migration@example.com', 'Migration')"
            )
            connection.exec_driver_sql("""
                INSERT INTO payment_methods
                    (id, user_id, name, type, is_main_bank, is_active, has_stamp_duty)
                VALUES ('bank-1', 'user-1', 'Bank', 'bank', 1, 1, 0)
            """)
            connection.exec_driver_sql("""
                INSERT INTO payment_methods
                    (id, user_id, name, type, linked_bank_id, is_main_bank, is_active, has_stamp_duty)
                VALUES ('card-1', 'user-1', 'Card', 'credit_card', 'bank-1', 0, 1, 0)
            """)
        command.upgrade(cfg, "head")
        with engine.connect() as connection:
            links = connection.exec_driver_sql("""
                SELECT user_id, card_payment_method_id, linked_bank_id, valid_from
                FROM card_bank_link_history
            """).mappings().all()
        assert links == [{
            "user_id": "user-1", "card_payment_method_id": "card-1",
            "linked_bank_id": "bank-1", "valid_from": "0001-01-01",
        }]
    finally:
        engine.dispose()
        os.unlink(db_path)


def test_migration_backfills_implicit_legacy_card_links_without_changing_bank_balances():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        cfg = _cfg(db_path)
        command.upgrade(cfg, "012pm_link_set_null")
        engine = create_engine(f"sqlite:///{db_path}")
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO users (id, email, name) VALUES ('user-1', 'migration@example.com', 'Migration')"
            )
            connection.exec_driver_sql("""
                INSERT INTO user_settings (user_id, key, value)
                VALUES ('user-1', 'tracking_start_date', '2026-01-01')
            """)
            connection.exec_driver_sql("""
                INSERT INTO payment_methods
                    (id, user_id, name, type, is_main_bank, is_active, has_stamp_duty)
                VALUES
                    ('bank-1', 'user-1', 'First bank', 'bank', 0, 1, 0),
                    ('bank-2', 'user-1', 'Second bank', 'bank', 1, 1, 0),
                    ('credit-1', 'user-1', 'Legacy credit', 'credit_card', 0, 1, 0),
                    ('debit-1', 'user-1', 'Legacy debit', 'debit_card', 0, 1, 0)
            """)
            connection.exec_driver_sql("""
                INSERT INTO main_bank_history
                    (id, user_id, payment_method_id, valid_from, opening_balance)
                VALUES
                    ('history-1', 'user-1', 'bank-1', '2026-01-01', 1000),
                    ('history-2', 'user-1', 'bank-2', '2026-03-01', 500)
            """)
            connection.exec_driver_sql("""
                INSERT INTO categories (id, user_id, type, sub_type, is_active)
                VALUES ('category-1', 'user-1', 'Housing', 'Rent', 1)
            """)
            connection.exec_driver_sql("""
                INSERT INTO transactions
                    (id, user_id, date, detail, amount, payment_method_id, category_id,
                     transaction_direction, billing_month)
                VALUES
                    ('transaction-1', 'user-1', '2025-12-15', 'Credit purchase', 100,
                     'credit-1', 'category-1', 'debit', '2026-01-01'),
                    ('transaction-2', 'user-1', '2026-03-15', 'Debit purchase', 50,
                     'debit-1', 'category-1', 'debit', '2026-03-01')
            """)

        command.upgrade(cfg, "head")

        with engine.connect() as connection:
            links = connection.exec_driver_sql("""
                SELECT card_payment_method_id, linked_bank_id, valid_from
                FROM card_bank_link_history
                ORDER BY card_payment_method_id, valid_from
            """).mappings().all()
            assert links == [
                {'card_payment_method_id': 'credit-1', 'linked_bank_id': 'bank-1', 'valid_from': '2026-01-01'},
                {'card_payment_method_id': 'credit-1', 'linked_bank_id': 'bank-2', 'valid_from': '2026-03-01'},
                {'card_payment_method_id': 'debit-1', 'linked_bank_id': 'bank-1', 'valid_from': '2026-01-01'},
                {'card_payment_method_id': 'debit-1', 'linked_bank_id': 'bank-2', 'valid_from': '2026-03-01'},
            ]
            current_links = connection.exec_driver_sql("""
                SELECT id, linked_bank_id FROM payment_methods
                WHERE id IN ('credit-1', 'debit-1') ORDER BY id
            """).mappings().all()
            assert current_links == [
                {'id': 'credit-1', 'linked_bank_id': 'bank-2'},
                {'id': 'debit-1', 'linked_bank_id': 'bank-2'},
            ]

        with Session(engine) as session:
            assert compute_bank_balance('user-1', 2026, 1, session) == 900.0
            assert compute_bank_balance('user-1', 2026, 3, session) == 450.0

        command.downgrade(cfg, "015account_identities")
        with engine.connect() as connection:
            assert connection.exec_driver_sql(
                "SELECT COUNT(*) FROM card_bank_link_history"
            ).scalar_one() == 0
            assert connection.exec_driver_sql("""
                SELECT COUNT(*) FROM payment_methods
                WHERE id IN ('credit-1', 'debit-1') AND linked_bank_id IS NULL
            """).scalar_one() == 2

        command.upgrade(cfg, "head")
        with Session(engine) as session:
            assert compute_bank_balance('user-1', 2026, 1, session) == 900.0
            assert compute_bank_balance('user-1', 2026, 3, session) == 450.0
    finally:
        engine.dispose()
        os.unlink(db_path)


def test_migration_removes_orphaned_financial_rows_without_touching_owned_data():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        cfg = _cfg(db_path)
        command.upgrade(cfg, "016legacy_card_links")
        engine = create_engine(f"sqlite:///{db_path}")
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO users (id, email, name) VALUES ('user-1', 'migration@example.com', 'Migration')"
            )
            connection.exec_driver_sql("""
                INSERT INTO salary_config
                    (id, user_id, valid_from, ral, employer_contrib_rate, voluntary_contrib_rate)
                VALUES
                    ('salary-owned', 'user-1', '2026-01-01', 60000, 0.02, 0.01),
                    ('salary-orphan', 'deleted-user', '2026-01-01', 60000, 0.02, 0.01)
            """)
            connection.exec_driver_sql("""
                INSERT INTO accounts
                    (id, user_id, type, name, opening_balance, is_active)
                VALUES
                    ('account-owned', 'user-1', 'investment', 'Owned', 1000, 1),
                    ('account-orphan', 'deleted-user', 'pension', 'Pension', 0, 1)
            """)
            connection.exec_driver_sql("""
                INSERT INTO assets
                    (id, user_id, year, asset_type, asset_name, account_id, manual_override)
                VALUES
                    ('asset-owned', 'user-1', 2026, 'investment', 'Owned', 'account-owned', 1200),
                    ('asset-cross-reference', 'user-1', 2026, 'pension', 'Pension', 'account-orphan', 500),
                    ('asset-orphan', 'deleted-user', 2026, 'pension', 'Pension', 'account-orphan', 500)
            """)
            connection.exec_driver_sql("""
                INSERT INTO transfers
                    (id, user_id, date, detail, amount, from_account_type, from_account_name,
                     to_account_type, to_account_name, billing_month, from_account_id)
                VALUES
                    ('transfer-cross-reference', 'user-1', '2026-01-01', 'Transfer', 100,
                     'pension', 'Pension', 'investment', 'Owned', '2026-01-01', 'account-orphan')
            """)

        command.upgrade(cfg, "head")

        with engine.connect() as connection:
            assert connection.exec_driver_sql(
                "SELECT id FROM salary_config ORDER BY id"
            ).scalars().all() == ['salary-owned']
            assert connection.exec_driver_sql(
                "SELECT id FROM assets ORDER BY id"
            ).scalars().all() == ['asset-cross-reference', 'asset-owned']
            assert connection.exec_driver_sql("""
                SELECT id, account_id FROM assets WHERE id = 'asset-cross-reference'
            """).mappings().one() == {
                'id': 'asset-cross-reference', 'account_id': None,
            }
            assert connection.exec_driver_sql("""
                SELECT id, from_account_id FROM transfers WHERE id = 'transfer-cross-reference'
            """).mappings().one() == {
                'id': 'transfer-cross-reference', 'from_account_id': None,
            }
            assert connection.exec_driver_sql(
                "SELECT id FROM accounts ORDER BY id"
            ).scalars().all() == ['account-owned']
            assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    finally:
        engine.dispose()
        os.unlink(db_path)


def test_migration_014_reconciles_legacy_rows_without_losing_constraints_or_indexes():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        cfg = _cfg(db_path)
        command.upgrade(cfg, "013card_link_history")
        with engine.begin() as connection:
            connection.exec_driver_sql("""
                INSERT INTO users (id, email, name, created_at)
                VALUES ('user-1', 'migration@example.com', 'Migration', NULL)
            """)
            connection.exec_driver_sql("""
                INSERT INTO user_settings (user_id, key, value, updated_at)
                VALUES ('user-1', 'setting', 'value', NULL)
            """)
            connection.exec_driver_sql("""
                INSERT INTO payment_methods
                    (id, user_id, name, type, is_main_bank, is_active, has_stamp_duty)
                VALUES ('bank-1', 'user-1', 'Bank', 'bank', 1, 1, 0)
            """)
            connection.exec_driver_sql("""
                INSERT INTO categories (id, user_id, type, sub_type, is_active)
                VALUES ('category-1', 'user-1', 'Housing', 'Rent', 1)
            """)
            connection.exec_driver_sql("""
                INSERT INTO forecasts (id, user_id, name, base_year, projection_years, created_at, updated_at)
                VALUES ('forecast-1', 'user-1', 'Forecast', 2026, 1, NULL, NULL)
            """)
            connection.exec_driver_sql("""
                INSERT INTO forecast_lines
                    (id, forecast_id, user_id, detail, base_amount, billing_day)
                VALUES ('line-1', 'forecast-1', 'user-1', 'Line', 10, 1)
            """)
            connection.exec_driver_sql("""
                INSERT INTO forecast_adjustments
                    (id, forecast_line_id, user_id, valid_from, new_amount, adjustment_type)
                VALUES ('adjustment-1', 'line-1', 'user-1', '2026-01-01', 20, NULL)
            """)
            connection.exec_driver_sql("""
                INSERT INTO transactions
                    (id, user_id, date, detail, amount, payment_method_id, category_id,
                     transaction_direction, billing_month, created_at, updated_at)
                VALUES ('transaction-1', 'user-1', '2026-01-01', 'Transaction', 10, 'bank-1', 'category-1',
                        'debit', '2026-01-01', NULL, NULL)
            """)
            connection.exec_driver_sql("""
                INSERT INTO transfers
                    (id, user_id, date, detail, amount, from_account_type, from_account_name,
                     to_account_type, to_account_name, billing_month, created_at)
                VALUES ('transfer-1', 'user-1', '2026-01-01', 'Transfer', 10, 'bank', 'Bank',
                        'saving', 'Savings', '2026-01-01', NULL)
            """)

        command.upgrade(cfg, "head")

        with engine.connect() as connection:
            adjustment_type = connection.exec_driver_sql("""
                SELECT adjustment_type FROM forecast_adjustments WHERE id = 'adjustment-1'
            """).scalar_one()
            assert adjustment_type == "fixed"
            for table_name, column_name, row_id in (
                ("users", "created_at", "user-1"),
                ("user_settings", "updated_at", "user-1"),
                ("forecasts", "created_at", "forecast-1"),
                ("forecasts", "updated_at", "forecast-1"),
                ("transactions", "created_at", "transaction-1"),
                ("transactions", "updated_at", "transaction-1"),
                ("transfers", "created_at", "transfer-1"),
            ):
                where = "user_id" if table_name == "user_settings" else "id"
                value = connection.exec_driver_sql(
                    f"SELECT {column_name} FROM {table_name} WHERE {where} = ?", (row_id,)
                ).scalar_one()
                assert value is not None

            assert connection.exec_driver_sql("SELECT COUNT(*) FROM transactions").scalar_one() == 1
            assert connection.exec_driver_sql("SELECT COUNT(*) FROM transfers").scalar_one() == 1

        inspector = inspect(engine)
        adjustment_checks = {
            constraint["name"] for constraint in inspector.get_check_constraints("forecast_adjustments")
        }
        assert "ck_adjustment_type" in adjustment_checks
        transaction_indexes = {idx["name"] for idx in inspector.get_indexes("transactions")}
        transfer_indexes = {idx["name"] for idx in inspector.get_indexes("transfers")}
        assert {"ix_transaction_user_date", "ix_transaction_user_billing_month"} <= transaction_indexes
        assert {"ix_transfer_user_billing_month", "ix_transfer_parent_id"} <= transfer_indexes
        transaction_fks = inspector.get_foreign_keys("transactions")
        payment_method_fks = [fk for fk in transaction_fks if fk["referred_table"] == "payment_methods"]
        assert len(payment_method_fks) == 1
        assert payment_method_fks[0]["options"].get("ondelete", "").upper() == "SET NULL"
    finally:
        engine.dispose()
        os.unlink(db_path)


def test_migration_015_backfills_account_ids_from_legacy_settings_and_transfers():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        cfg = _cfg(db_path)
        command.upgrade(cfg, "014reconcile_schema")
        engine = create_engine(f"sqlite:///{db_path}")
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO users (id, email, name) VALUES ('user-1', 'migration@example.com', 'Migration')"
            )
            connection.exec_driver_sql(
                "INSERT INTO user_settings (user_id, key, value) VALUES (?, ?, ?)",
                ('user-1', 'opening_saving_balance_Nest', '3000'),
            )
            connection.exec_driver_sql("""
                INSERT INTO payment_methods (id, user_id, name, type, is_main_bank, is_active, has_stamp_duty)
                VALUES ('bank-1', 'user-1', 'Bank', 'bank', 1, 1, 0)
            """)
            connection.exec_driver_sql("""
                INSERT INTO transfers
                    (id, user_id, date, detail, amount, from_account_type, from_account_name,
                     to_account_type, to_account_name, billing_month)
                VALUES ('transfer-1', 'user-1', '2026-01-01', 'Transfer', 100, 'bank', 'Bank',
                        'saving', 'Nest', '2026-01-01')
            """)
            connection.exec_driver_sql("""
                INSERT INTO assets (id, user_id, year, asset_type, asset_name, manual_override)
                VALUES ('asset-1', 'user-1', 2026, 'saving', 'Nest', 3500)
            """)
        command.upgrade(cfg, "head")
        with engine.connect() as connection:
            account = connection.exec_driver_sql("""
                SELECT id, opening_balance FROM accounts
                WHERE user_id = 'user-1' AND type = 'saving' AND name = 'Nest'
            """).mappings().one()
            transfer = connection.exec_driver_sql("""
                SELECT from_payment_method_id, to_account_id FROM transfers WHERE id = 'transfer-1'
            """).mappings().one()
            asset_account_id = connection.exec_driver_sql(
                "SELECT account_id FROM assets WHERE id = 'asset-1'"
            ).scalar_one()
            assert account['opening_balance'] == 3000
            assert transfer == {'from_payment_method_id': 'bank-1', 'to_account_id': account['id']}
            assert asset_account_id == account['id']
            assert connection.exec_driver_sql("""
                SELECT COUNT(*) FROM user_settings
                WHERE key = 'opening_saving_balance_Nest'
            """).scalar_one() == 0
    finally:
        engine.dispose()
        os.unlink(db_path)


def test_migration_015_normalizes_unsafe_legacy_opening_balances():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        cfg = _cfg(db_path)
        command.upgrade(cfg, "014reconcile_schema")
        engine = create_engine(f"sqlite:///{db_path}")
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO users (id, email, name) VALUES ('user-1', 'migration@example.com', 'Migration')"
            )
            for name, value in {
                "NaN": "NaN",
                "PositiveInfinity": "Infinity",
                "NegativeInfinity": "-Infinity",
                "Malformed": "not-a-number",
                "Overflow": "10000000000.00",
            }.items():
                connection.exec_driver_sql(
                    "INSERT INTO user_settings (user_id, key, value) VALUES (?, ?, ?)",
                    ("user-1", f"opening_saving_balance_{name}", value),
                )

        command.upgrade(cfg, "head")

        with engine.connect() as connection:
            balances = connection.exec_driver_sql(
                "SELECT name, opening_balance FROM accounts ORDER BY name"
            ).mappings().all()
        assert [row["name"] for row in balances] == [
            "Malformed", "NaN", "NegativeInfinity", "Overflow", "PositiveInfinity",
        ]
        assert all(Decimal(str(row["opening_balance"])).is_finite() for row in balances)
        assert all(Decimal(str(row["opening_balance"])) == Decimal("0") for row in balances)
    finally:
        engine.dispose()
        os.unlink(db_path)


def test_migration_015_downgrade_recreates_legacy_settings_for_reupgrade():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        cfg = _cfg(db_path)
        command.upgrade(cfg, "014reconcile_schema")
        engine = create_engine(f"sqlite:///{db_path}")
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO users (id, email, name) VALUES ('user-1', 'migration@example.com', 'Migration')"
            )
            connection.exec_driver_sql(
                "INSERT INTO user_settings (user_id, key, value) VALUES (?, ?, ?)",
                ("user-1", "opening_saving_balance_Nest", "3000.00"),
            )
            connection.exec_driver_sql("""
                INSERT INTO payment_methods (id, user_id, name, type, is_main_bank, is_active, has_stamp_duty)
                VALUES ('bank-1', 'user-1', 'Bank', 'bank', 1, 1, 0)
            """)
            connection.exec_driver_sql("""
                INSERT INTO transfers
                    (id, user_id, date, detail, amount, from_account_type, from_account_name,
                     to_account_type, to_account_name, billing_month)
                VALUES ('transfer-1', 'user-1', '2026-01-01', 'Transfer', 100, 'bank', 'Bank',
                        'saving', 'Nest', '2026-01-01')
            """)

        command.upgrade(cfg, "head")
        with engine.connect() as connection:
            first_account_id = connection.exec_driver_sql("""
                SELECT id FROM accounts
                WHERE user_id = 'user-1' AND type = 'saving' AND name = 'Nest'
            """).scalar_one()
            assert connection.exec_driver_sql(
                "SELECT to_account_id FROM transfers WHERE id = 'transfer-1'"
            ).scalar_one() == first_account_id

        command.downgrade(cfg, "014reconcile_schema")
        with engine.connect() as connection:
            legacy_balance = connection.exec_driver_sql("""
                SELECT value FROM user_settings
                WHERE user_id = 'user-1' AND key = 'opening_saving_balance_Nest'
            """).scalar_one()
            assert Decimal(legacy_balance) == Decimal("3000.00")
            assert connection.exec_driver_sql(
                "SELECT to_account_name FROM transfers WHERE id = 'transfer-1'"
            ).scalar_one() == "Nest"

        command.upgrade(cfg, "head")
        with engine.connect() as connection:
            reupgraded_account_id = connection.exec_driver_sql("""
                SELECT id FROM accounts
                WHERE user_id = 'user-1' AND type = 'saving' AND name = 'Nest'
                  AND opening_balance = 3000
            """).scalar_one()
            assert connection.exec_driver_sql(
                "SELECT to_account_id FROM transfers WHERE id = 'transfer-1'"
            ).scalar_one() == reupgraded_account_id
    finally:
        engine.dispose()
        os.unlink(db_path)


def test_migration_015_roundtrip_refreshes_renamed_account_history_per_owner_and_type():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        cfg = _cfg(db_path)
        command.upgrade(cfg, "014reconcile_schema")
        engine = create_engine(f"sqlite:///{db_path}")
        with engine.begin() as connection:
            connection.exec_driver_sql("""
                INSERT INTO users (id, email, name) VALUES
                ('user-1', 'alice@example.com', 'Alice'),
                ('user-2', 'bob@example.com', 'Bob')
            """)
            for user_id, account_type, name in (
                ("user-1", "saving", "Alice saving"),
                ("user-1", "investment", "Alice investment"),
                ("user-2", "saving", "Bob saving"),
                ("user-2", "investment", "Bob investment"),
            ):
                connection.exec_driver_sql(
                    "INSERT INTO user_settings (user_id, key, value) VALUES (?, ?, '100')",
                    (user_id, f"opening_{account_type}_balance_{name}"),
                )
            for transfer_id, user_id, saving_name, investment_name in (
                ("transfer-alice", "user-1", "Alice saving", "Alice investment"),
                ("transfer-bob", "user-2", "Bob saving", "Bob investment"),
                ("transfer-cross-owner", "user-1", "Alice saving", "Alice investment"),
            ):
                connection.exec_driver_sql("""
                    INSERT INTO transfers
                        (id, user_id, date, detail, amount, from_account_type, from_account_name,
                         to_account_type, to_account_name, billing_month)
                    VALUES (?, ?, '2026-01-01', 'Transfer', 100, 'saving', ?, 'investment', ?, '2026-01-01')
                """, (transfer_id, user_id, saving_name, investment_name))
            for asset_id, user_id, account_type, name in (
                ("asset-alice-saving", "user-1", "saving", "Alice saving"),
                ("asset-alice-investment", "user-1", "investment", "Alice investment"),
                ("asset-bob-saving", "user-2", "saving", "Bob saving"),
                ("asset-bob-investment", "user-2", "investment", "Bob investment"),
                ("asset-cross-type", "user-1", "saving", "Alice saving"),
            ):
                connection.exec_driver_sql("""
                    INSERT INTO assets (id, user_id, year, asset_type, asset_name, manual_override)
                    VALUES (?, ?, 2026, ?, ?, 200)
                """, (asset_id, user_id, account_type, name))

        command.upgrade(cfg, "head")
        with engine.begin() as connection:
            for user_id, account_type, name in (
                ("user-1", "saving", "Alice renamed saving"),
                ("user-1", "investment", "Alice renamed investment"),
                ("user-2", "saving", "Bob renamed saving"),
                ("user-2", "investment", "Bob renamed investment"),
            ):
                connection.exec_driver_sql("""
                    UPDATE accounts SET name = ?
                    WHERE user_id = ? AND type = ?
                """, (name, user_id, account_type))
            # These references are valid foreign keys but invalid ownership/type
            # relationships, so their legacy snapshots must not be overwritten.
            connection.exec_driver_sql("""
                UPDATE transfers SET from_account_id = (
                    SELECT id FROM accounts WHERE user_id = 'user-2' AND type = 'saving'
                ) WHERE id = 'transfer-cross-owner'
            """)
            connection.exec_driver_sql("""
                UPDATE assets SET account_id = (
                    SELECT id FROM accounts WHERE user_id = 'user-1' AND type = 'investment'
                ) WHERE id = 'asset-cross-type'
            """)

        command.downgrade(cfg, "014reconcile_schema")
        with engine.connect() as connection:
            assert connection.exec_driver_sql("""
                SELECT id, from_account_name, to_account_name FROM transfers
                WHERE id IN ('transfer-alice', 'transfer-bob', 'transfer-cross-owner') ORDER BY id
            """).mappings().all() == [
                {'id': 'transfer-alice', 'from_account_name': 'Alice renamed saving', 'to_account_name': 'Alice renamed investment'},
                {'id': 'transfer-bob', 'from_account_name': 'Bob renamed saving', 'to_account_name': 'Bob renamed investment'},
                {'id': 'transfer-cross-owner', 'from_account_name': 'Alice saving', 'to_account_name': 'Alice renamed investment'},
            ]
            assert connection.exec_driver_sql("""
                SELECT id, asset_name FROM assets
                WHERE id IN ('asset-alice-saving', 'asset-alice-investment', 'asset-bob-saving',
                             'asset-bob-investment', 'asset-cross-type')
                ORDER BY id
            """).mappings().all() == [
                {'id': 'asset-alice-investment', 'asset_name': 'Alice renamed investment'},
                {'id': 'asset-alice-saving', 'asset_name': 'Alice renamed saving'},
                {'id': 'asset-bob-investment', 'asset_name': 'Bob renamed investment'},
                {'id': 'asset-bob-saving', 'asset_name': 'Bob renamed saving'},
                {'id': 'asset-cross-type', 'asset_name': 'Alice saving'},
            ]

        command.upgrade(cfg, "head")
        with engine.connect() as connection:
            transfer_accounts = connection.exec_driver_sql("""
                SELECT transfers.id, from_accounts.user_id AS from_user, from_accounts.type AS from_type,
                       from_accounts.name AS from_name, to_accounts.user_id AS to_user,
                       to_accounts.type AS to_type, to_accounts.name AS to_name
                FROM transfers
                JOIN accounts AS from_accounts ON from_accounts.id = transfers.from_account_id
                JOIN accounts AS to_accounts ON to_accounts.id = transfers.to_account_id
                WHERE transfers.id IN ('transfer-alice', 'transfer-bob')
                ORDER BY transfers.id
            """).mappings().all()
            assert transfer_accounts == [
                {'id': 'transfer-alice', 'from_user': 'user-1', 'from_type': 'saving', 'from_name': 'Alice renamed saving', 'to_user': 'user-1', 'to_type': 'investment', 'to_name': 'Alice renamed investment'},
                {'id': 'transfer-bob', 'from_user': 'user-2', 'from_type': 'saving', 'from_name': 'Bob renamed saving', 'to_user': 'user-2', 'to_type': 'investment', 'to_name': 'Bob renamed investment'},
            ]
            asset_accounts = connection.exec_driver_sql("""
                SELECT assets.id, accounts.user_id, accounts.type, accounts.name
                FROM assets JOIN accounts ON accounts.id = assets.account_id
                WHERE assets.id IN ('asset-alice-saving', 'asset-alice-investment',
                                    'asset-bob-saving', 'asset-bob-investment')
                ORDER BY assets.id
            """).mappings().all()
            assert asset_accounts == [
                {'id': 'asset-alice-investment', 'user_id': 'user-1', 'type': 'investment', 'name': 'Alice renamed investment'},
                {'id': 'asset-alice-saving', 'user_id': 'user-1', 'type': 'saving', 'name': 'Alice renamed saving'},
                {'id': 'asset-bob-investment', 'user_id': 'user-2', 'type': 'investment', 'name': 'Bob renamed investment'},
                {'id': 'asset-bob-saving', 'user_id': 'user-2', 'type': 'saving', 'name': 'Bob renamed saving'},
            ]
            assert connection.exec_driver_sql("""
                SELECT from_account_id FROM transfers WHERE id = 'transfer-cross-owner'
            """).scalar_one() is None
            assert connection.exec_driver_sql("""
                SELECT account_id FROM assets WHERE id = 'asset-cross-type'
            """).scalar_one() is None
    finally:
        engine.dispose()
        os.unlink(db_path)


def test_migration_015_roundtrip_restores_pension_identity_from_legacy_history():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        cfg = _cfg(db_path)
        command.upgrade(cfg, "014reconcile_schema")
        engine = create_engine(f"sqlite:///{db_path}")
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO users (id, email, name) VALUES ('user-1', 'migration@example.com', 'Migration')"
            )
            connection.exec_driver_sql(
                "INSERT INTO users (id, email, name) VALUES ('user-2', 'other@example.com', 'Other')"
            )
            connection.exec_driver_sql("""
                INSERT INTO salary_config
                    (id, user_id, valid_from, ral, employer_contrib_rate, voluntary_contrib_rate)
                VALUES ('salary-1', 'user-1', '2026-01-01', 60000, 0.04, 0.01)
            """)
            connection.exec_driver_sql("""
                INSERT INTO payment_methods
                    (id, user_id, name, type, is_main_bank, is_active, has_stamp_duty)
                VALUES ('bank-1', 'user-1', 'Bank', 'bank', 1, 1, 0)
            """)
            connection.exec_driver_sql("""
                INSERT INTO transfers
                    (id, user_id, date, detail, amount, from_account_type, from_account_name,
                     to_account_type, to_account_name, billing_month)
                VALUES ('transfer-1', 'user-1', '2026-04-01', 'Pension contribution', 123.45,
                        'bank', 'Bank', 'pension', 'Pension', '2026-04-01')
            """)
            connection.exec_driver_sql("""
                INSERT INTO assets (id, user_id, year, asset_type, asset_name, manual_override)
                VALUES ('asset-1', 'user-1', 2026, 'pension', 'Pension', 4321.50)
            """)
            connection.exec_driver_sql("""
                INSERT INTO assets (id, user_id, year, asset_type, asset_name, manual_override)
                VALUES ('asset-2', 'user-2', 2026, 'pension', 'Pension', 678.90)
            """)

        command.upgrade(cfg, "head")
        with engine.connect() as connection:
            initial_account_id = connection.exec_driver_sql("""
                SELECT id FROM accounts
                WHERE user_id = 'user-1' AND type = 'pension' AND name = 'Pension'
            """).scalar_one()
            assert connection.exec_driver_sql(
                "SELECT to_account_id FROM transfers WHERE id = 'transfer-1'"
            ).scalar_one() == initial_account_id
            assert connection.exec_driver_sql(
                "SELECT account_id FROM assets WHERE id = 'asset-1'"
            ).scalar_one() == initial_account_id

        with engine.begin() as connection:
            connection.exec_driver_sql("""
                UPDATE salary_config
                SET employer_contrib_rate = 0, voluntary_contrib_rate = 0
                WHERE id = 'salary-1'
            """)

        command.downgrade(cfg, "014reconcile_schema")
        with engine.connect() as connection:
            transfer = connection.exec_driver_sql("""
                SELECT amount, date, detail, to_account_type, to_account_name
                FROM transfers WHERE id = 'transfer-1'
            """).mappings().one()
            asset = connection.exec_driver_sql("""
                SELECT year, asset_type, asset_name, manual_override
                FROM assets WHERE id = 'asset-1'
            """).mappings().one()
            assert transfer == {
                'amount': 123.45,
                'date': '2026-04-01',
                'detail': 'Pension contribution',
                'to_account_type': 'pension',
                'to_account_name': 'Pension',
            }
            assert asset == {
                'year': 2026,
                'asset_type': 'pension',
                'asset_name': 'Pension',
                'manual_override': 4321.5,
            }

        command.upgrade(cfg, "head")
        with engine.connect() as connection:
            pension_rows = connection.exec_driver_sql("""
                SELECT id, user_id FROM accounts
                WHERE user_id = 'user-1' AND type = 'pension' AND name = 'Pension'
            """).mappings().all()
            assert len(pension_rows) == 1
            pension_account_id = pension_rows[0]['id']
            assert pension_rows[0]['user_id'] == 'user-1'
            transfer = connection.exec_driver_sql("""
                SELECT amount, date, detail, to_account_id
                FROM transfers WHERE id = 'transfer-1'
            """).mappings().one()
            asset = connection.exec_driver_sql("""
                SELECT year, asset_type, asset_name, manual_override, account_id
                FROM assets WHERE id = 'asset-1'
            """).mappings().one()
            assert transfer == {
                'amount': 123.45,
                'date': '2026-04-01',
                'detail': 'Pension contribution',
                'to_account_id': pension_account_id,
            }
            assert asset == {
                'year': 2026,
                'asset_type': 'pension',
                'asset_name': 'Pension',
                'manual_override': 4321.5,
                'account_id': pension_account_id,
            }
            linked_asset_owners = connection.exec_driver_sql("""
                SELECT assets.user_id AS asset_user_id, accounts.user_id AS account_user_id
                FROM assets JOIN accounts ON accounts.id = assets.account_id
                WHERE assets.id IN ('asset-1', 'asset-2')
                ORDER BY assets.id
            """).mappings().all()
            assert linked_asset_owners == [
                {'asset_user_id': 'user-1', 'account_user_id': 'user-1'},
                {'asset_user_id': 'user-2', 'account_user_id': 'user-2'},
            ]

        command.upgrade(cfg, "head")
        with engine.connect() as connection:
            assert connection.exec_driver_sql("""
                SELECT COUNT(*) FROM accounts
                WHERE user_id = 'user-1' AND type = 'pension' AND name = 'Pension'
            """).scalar_one() == 1
    finally:
        engine.dispose()
        os.unlink(db_path)


def test_migration_003_roundtrip_preserves_user_id_index():
    """Downgrade to 002 then re-upgrade to head must preserve ix_main_bank_history_user_id."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        command.upgrade(_cfg(db_path), "head")
        command.downgrade(_cfg(db_path), "002")
        command.upgrade(_cfg(db_path), "head")

        inspector = inspect(engine)
        index_names = {idx["name"] for idx in inspector.get_indexes("main_bank_history")}
        assert "ix_main_bank_history_user_id" in index_names, (
            f"ix_main_bank_history_user_id missing after downgrade+upgrade. Found: {index_names}"
        )
    finally:
        engine.dispose()
        command.downgrade(_cfg(db_path), "base")
        os.unlink(db_path)
