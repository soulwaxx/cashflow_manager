"""Reconcile migrated schema with ORM metadata.

Revision ID: 014reconcile_schema
Revises: 013card_link_history
Create Date: 2026-09-20

SQLite requires table recreation to add NOT NULL constraints.  Null legacy
values are backfilled before that recreation so existing rows remain valid.
"""
from alembic import op
import sqlalchemy as sa


revision = "014reconcile_schema"
down_revision = "013card_link_history"
branch_labels = None
depends_on = None


_TIMESTAMP_COLUMNS = {
    "forecasts": ("created_at", "updated_at"),
    "transactions": ("created_at", "updated_at"),
    "transfers": ("created_at",),
    "user_settings": ("updated_at",),
    "users": ("created_at",),
}


def upgrade() -> None:
    op.execute(sa.text("""
        UPDATE forecast_adjustments
        SET adjustment_type = 'fixed'
        WHERE adjustment_type IS NULL
    """))
    for table_name, column_names in _TIMESTAMP_COLUMNS.items():
        for column_name in column_names:
            op.execute(sa.text(
                f"UPDATE {table_name} SET {column_name} = CURRENT_TIMESTAMP "
                f"WHERE {column_name} IS NULL"
            ))

    with op.batch_alter_table("forecast_adjustments", recreate="always") as batch_op:
        batch_op.alter_column(
            "adjustment_type",
            existing_type=sa.String(length=20),
            nullable=False,
        )

    for table_name, column_names in _TIMESTAMP_COLUMNS.items():
        with op.batch_alter_table(table_name, recreate="always") as batch_op:
            for column_name in column_names:
                batch_op.alter_column(
                    column_name,
                    existing_type=sa.DateTime(),
                    nullable=False,
                )

    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_oidc_sub", "users", ["oidc_sub"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_oidc_sub", table_name="users")
    op.drop_index("ix_users_email", table_name="users")

    for table_name, column_names in _TIMESTAMP_COLUMNS.items():
        with op.batch_alter_table(table_name, recreate="always") as batch_op:
            for column_name in column_names:
                batch_op.alter_column(
                    column_name,
                    existing_type=sa.DateTime(),
                    nullable=True,
                )

    with op.batch_alter_table("forecast_adjustments", recreate="always") as batch_op:
        batch_op.alter_column(
            "adjustment_type",
            existing_type=sa.String(length=20),
            nullable=True,
        )
