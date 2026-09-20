"""Remove financial rows left behind by deleted users.

Revision ID: 017remove_orphans
Revises: 016legacy_card_links
Create Date: 2026-09-20

Older SQLite connections did not always enforce foreign-key cascades. Salary
configurations and asset overrides belonging to users that no longer exist are
inaccessible and cannot be assigned safely, so remove them. Migration 015 may
also have created pension accounts for those orphaned salary rows; remove those
accounts after clearing any unexpected references to them.

This cleanup is intentionally irreversible. Restore a pre-upgrade database
backup if the deleted orphan data must be recovered.
"""
from alembic import op
import sqlalchemy as sa


revision = "017remove_orphans"
down_revision = "016legacy_card_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("""
        DELETE FROM assets
        WHERE NOT EXISTS (
            SELECT 1 FROM users WHERE users.id = assets.user_id
        )
    """))
    bind.execute(sa.text("""
        DELETE FROM salary_config
        WHERE NOT EXISTS (
            SELECT 1 FROM users WHERE users.id = salary_config.user_id
        )
    """))

    for table_name, column_name in (
        ("assets", "account_id"),
        ("transfers", "from_account_id"),
        ("transfers", "to_account_id"),
    ):
        bind.execute(sa.text(f"""
            UPDATE {table_name}
            SET {column_name} = NULL
            WHERE {column_name} IN (
                SELECT accounts.id
                FROM accounts
                WHERE NOT EXISTS (
                    SELECT 1 FROM users WHERE users.id = accounts.user_id
                )
            )
        """))

    bind.execute(sa.text("""
        DELETE FROM accounts
        WHERE NOT EXISTS (
            SELECT 1 FROM users WHERE users.id = accounts.user_id
        )
    """))


def downgrade() -> None:
    # Deleted orphan rows cannot be reconstructed or reassigned safely.
    pass
