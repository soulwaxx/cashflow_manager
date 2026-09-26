"""Remove the retired forecasting feature and its saved scenarios.

Revision ID: 018remove_forecasting
Revises: 017remove_orphans

Irreversible data loss: back up the database before upgrading. A downgrade
cannot restore forecasts, lines, or adjustments from a previous installation.
"""
from alembic import op


revision = "018remove_forecasting"
down_revision = "017remove_orphans"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("forecast_adjustments")
    op.drop_table("forecast_lines")
    op.drop_table("forecasts")


def downgrade() -> None:
    raise RuntimeError("Forecast data cannot be restored; use a pre-upgrade database backup")
