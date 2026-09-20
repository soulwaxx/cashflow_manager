"""Backfill implicit links for legacy bank-funded cards.

Revision ID: 016legacy_card_links
Revises: 015account_identities
Create Date: 2026-09-20

Before card links were explicit, every debit, credit, and revolving card affected
whichever main bank was active for the billing month. Preserve that behavior by
copying each user's main-bank history to legacy cards that have neither a current
link nor link history.
"""
import uuid
from collections import defaultdict

from alembic import op
import sqlalchemy as sa


revision = "016legacy_card_links"
down_revision = "015account_identities"
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


def _month_start(value: str) -> str:
    year, month, _ = value.split("-", 2)
    return f"{int(year):04d}-{int(month):02d}-01"


def _inferred_link_id(card_id: str, linked_bank_id: str, valid_from: str) -> str:
    return str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"cashflow-manager:migration-016:{card_id}:{linked_bank_id}:{valid_from}",
    ))


def upgrade() -> None:
    bind = op.get_bind()
    legacy_cards = bind.execute(sa.text("""
        SELECT card.id, card.user_id
        FROM payment_methods AS card
        WHERE card.type IN ('debit_card', 'credit_card', 'revolving')
          AND card.linked_bank_id IS NULL
          AND NOT EXISTS (
              SELECT 1
              FROM card_bank_link_history AS link
              WHERE link.card_payment_method_id = card.id
          )
        ORDER BY card.user_id, card.id
    """)).mappings().all()
    if not legacy_cards:
        return

    target_users = {card["user_id"] for card in legacy_cards}
    histories_by_user: dict[str, dict[str, str]] = defaultdict(dict)
    history_rows = bind.execute(sa.text("""
        SELECT history.user_id, history.payment_method_id, history.valid_from
        FROM main_bank_history AS history
        JOIN payment_methods AS bank
          ON bank.id = history.payment_method_id
         AND bank.user_id = history.user_id
         AND bank.type = 'bank'
        ORDER BY history.user_id, history.valid_from, history.id
    """)).mappings()
    for row in history_rows:
        if row["user_id"] in target_users:
            histories_by_user[row["user_id"]][_month_start(row["valid_from"])] = row["payment_method_id"]

    links = []
    current_links = {}
    for card in legacy_cards:
        periods = histories_by_user.get(card["user_id"], {})
        for valid_from, linked_bank_id in periods.items():
            links.append({
                "id": _inferred_link_id(card["id"], linked_bank_id, valid_from),
                "user_id": card["user_id"],
                "card_payment_method_id": card["id"],
                "linked_bank_id": linked_bank_id,
                "valid_from": valid_from,
            })
        if periods:
            current_links[card["id"]] = periods[max(periods)]

    if links:
        bind.execute(card_bank_link_history.insert(), links)
    for card_id, linked_bank_id in current_links.items():
        bind.execute(
            sa.text("UPDATE payment_methods SET linked_bank_id = :linked_bank_id WHERE id = :card_id"),
            {"card_id": card_id, "linked_bank_id": linked_bank_id},
        )


def downgrade() -> None:
    bind = op.get_bind()
    generated_by_card: dict[str, set[str]] = defaultdict(set)
    rows = bind.execute(sa.text("""
        SELECT id, card_payment_method_id, linked_bank_id, valid_from
        FROM card_bank_link_history
    """)).mappings().all()
    for row in rows:
        expected_id = _inferred_link_id(
            row["card_payment_method_id"], row["linked_bank_id"], row["valid_from"]
        )
        if row["id"] != expected_id:
            continue
        generated_by_card[row["card_payment_method_id"]].add(row["linked_bank_id"])
        bind.execute(
            sa.text("DELETE FROM card_bank_link_history WHERE id = :id"),
            {"id": row["id"]},
        )

    for card_id, inferred_bank_ids in generated_by_card.items():
        remaining_links = bind.execute(
            sa.text("""
                SELECT COUNT(*) FROM card_bank_link_history
                WHERE card_payment_method_id = :card_id
            """),
            {"card_id": card_id},
        ).scalar_one()
        if not remaining_links:
            bind.execute(
                sa.text("""
                    UPDATE payment_methods SET linked_bank_id = NULL
                    WHERE id = :card_id AND linked_bank_id IN :inferred_bank_ids
                """).bindparams(sa.bindparam("inferred_bank_ids", expanding=True)),
                {"card_id": card_id, "inferred_bank_ids": sorted(inferred_bank_ids)},
            )
