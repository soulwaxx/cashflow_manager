"""Add effective-dated card-to-bank link history.

Revision ID: 013card_link_history
Revises: 012pm_link_set_null
Create Date: 2026-09-19

Existing card links are copied as a baseline effective from ``0001-01-01`` so
all previously recorded billing periods retain their current routing.
"""
import uuid

from alembic import op
import sqlalchemy as sa


revision = "013card_link_history"
down_revision = "012pm_link_set_null"
branch_labels = None
depends_on = None


card_bank_link_history = sa.table(
    "card_bank_link_history",
    sa.column("id", sa.String(36)),
    sa.column("user_id", sa.String(36)),
    sa.column("card_payment_method_id", sa.String(36)),
    sa.column("linked_bank_id", sa.String(36)),
    sa.column("valid_from", sa.String(10)),
)


def upgrade() -> None:
    op.create_table(
        "card_bank_link_history",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "card_payment_method_id", sa.String(36),
            sa.ForeignKey("payment_methods.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "linked_bank_id", sa.String(36),
            sa.ForeignKey("payment_methods.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("valid_from", sa.String(10), nullable=False),
        sa.UniqueConstraint("card_payment_method_id", "valid_from", name="uq_card_bank_link_effective"),
    )
    op.create_index("ix_card_bank_link_history_user_id", "card_bank_link_history", ["user_id"])
    op.create_index(
        "ix_card_bank_link_history_card_payment_method_id",
        "card_bank_link_history",
        ["card_payment_method_id"],
    )

    bind = op.get_bind()
    rows = bind.execute(sa.text("""
        SELECT card.id, card.user_id, card.linked_bank_id
        FROM payment_methods AS card
        JOIN payment_methods AS bank
          ON bank.id = card.linked_bank_id AND bank.user_id = card.user_id
        WHERE card.type IN ('debit_card', 'credit_card', 'revolving')
          AND card.linked_bank_id IS NOT NULL
          AND bank.type = 'bank'
    """)).mappings()
    links = [
        {
            "id": str(uuid.uuid4()),
            "user_id": row["user_id"],
            "card_payment_method_id": row["id"],
            "linked_bank_id": row["linked_bank_id"],
            "valid_from": "0001-01-01",
        }
        for row in rows
    ]
    if links:
        bind.execute(card_bank_link_history.insert(), links)


def downgrade() -> None:
    op.drop_index("ix_card_bank_link_history_card_payment_method_id", table_name="card_bank_link_history")
    op.drop_index("ix_card_bank_link_history_user_id", table_name="card_bank_link_history")
    op.drop_table("card_bank_link_history")
