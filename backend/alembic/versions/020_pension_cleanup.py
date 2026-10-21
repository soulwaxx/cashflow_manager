"""Remove superseded salary pension rates and computed-net cache.

Revision ID: 020pension_cleanup
Revises: 019pension_foundation
"""
from alembic import op

revision = "020pension_cleanup"
down_revision = "019pension_foundation"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("salary_config") as batch_op:
        batch_op.drop_column("employer_contrib_rate")
        batch_op.drop_column("voluntary_contrib_rate")
        batch_op.drop_column("computed_net_monthly")


def downgrade():
    raise RuntimeError(
        "Pension cleanup cannot be downgraded losslessly; restore a pre-upgrade database backup"
    )
