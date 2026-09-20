# backend/tests/test_migrations.py
import os
import tempfile
import pytest
from sqlalchemy import create_engine, inspect
from alembic import command
from alembic.config import Config


def _cfg(db_path: str) -> Config:
    """Return Alembic config pointed at a temp DB."""
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    cfg.set_main_option(
        "script_location",
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "alembic")),
    )
    return cfg


def test_migration_head_creates_expected_schema():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        command.upgrade(_cfg(db_path), "head")
        engine = create_engine(f"sqlite:///{db_path}")
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

        # forecasts — datetime columns
        forecast_cols = {c["name"]: c for c in inspector.get_columns("forecasts")}
        assert "created_at" in forecast_cols
        assert "updated_at" in forecast_cols

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
    finally:
        os.unlink(db_path)


def test_migration_013_backfills_current_card_links_from_previous_head():
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
        os.unlink(db_path)


def test_migration_003_roundtrip_preserves_user_id_index():
    """Downgrade to 002 then re-upgrade to head must preserve ix_main_bank_history_user_id."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        command.upgrade(_cfg(db_path), "head")
        command.downgrade(_cfg(db_path), "002")
        command.upgrade(_cfg(db_path), "head")

        engine = create_engine(f"sqlite:///{db_path}")
        inspector = inspect(engine)
        index_names = {idx["name"] for idx in inspector.get_indexes("main_bank_history")}
        assert "ix_main_bank_history_user_id" in index_names, (
            f"ix_main_bank_history_user_id missing after downgrade+upgrade. Found: {index_names}"
        )
    finally:
        command.downgrade(_cfg(db_path), "base")
        os.unlink(db_path)
