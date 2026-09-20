"""Replace mutable non-bank account names with owned stable identities.

Revision ID: 015account_identities
Revises: 014reconcile_schema
Create Date: 2026-09-21

Legacy opening-balance settings become account rows. Existing transfer and asset
references are backfilled only when their old names resolve to an owned account;
unresolved historical rows are preserved with a null stable reference.
"""
import uuid
from decimal import Decimal, InvalidOperation

from alembic import op
import sqlalchemy as sa


revision = "015account_identities"
down_revision = "014reconcile_schema"
branch_labels = None
depends_on = None


accounts = sa.table(
    "accounts",
    sa.column("id", sa.String(36)),
    sa.column("user_id", sa.String(36)),
    sa.column("type", sa.String(20)),
    sa.column("name", sa.String(255)),
    sa.column("opening_balance", sa.Numeric(12, 2)),
    sa.column("is_active", sa.Boolean()),
)


_ZERO_OPENING_BALANCE = Decimal("0")
_OPENING_BALANCE_QUANTUM = Decimal("0.01")
_OPENING_BALANCE_MAX = Decimal("9999999999.99")


def _opening_balance(value: object) -> Decimal:
    """Return a finite value representable by accounts.opening_balance.

    The legacy settings API accepted arbitrary strings. Invalid, non-finite,
    over-precision, and out-of-range values retain the historical safe zero
    default rather than preventing migration startup or persisting invalid money.
    """
    try:
        balance = Decimal(str(value))
        normalized = balance.quantize(_OPENING_BALANCE_QUANTUM)
    except (InvalidOperation, TypeError, ValueError):
        return _ZERO_OPENING_BALANCE
    if (
        not balance.is_finite()
        or normalized != balance
        or abs(normalized) > _OPENING_BALANCE_MAX
    ):
        return _ZERO_OPENING_BALANCE
    return normalized


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("opening_balance", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.UniqueConstraint("user_id", "type", "name", name="uq_account_user_type_name"),
    )
    op.create_index("ix_accounts_user_id", "accounts", ["user_id"])

    with op.batch_alter_table("transfers", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("from_account_id", sa.String(36), nullable=True))
        batch_op.add_column(sa.Column("to_account_id", sa.String(36), nullable=True))
        batch_op.create_foreign_key(
            "fk_transfers_from_account_id", "accounts", ["from_account_id"], ["id"], ondelete="SET NULL"
        )
        batch_op.create_foreign_key(
            "fk_transfers_to_account_id", "accounts", ["to_account_id"], ["id"], ondelete="SET NULL"
        )

    with op.batch_alter_table("assets", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("account_id", sa.String(36), nullable=True))
        batch_op.create_foreign_key(
            "fk_assets_account_id", "accounts", ["account_id"], ["id"], ondelete="SET NULL"
        )

    bind = op.get_bind()
    setting_rows = bind.execute(sa.text("""
        SELECT user_id, key, value
        FROM user_settings
        WHERE key LIKE 'opening_saving_balance_%'
           OR key LIKE 'opening_investment_balance_%'
    """)).mappings().all()

    account_rows = []
    account_ids: dict[tuple[str, str, str], str] = {}
    migrated_setting_keys = []
    for row in setting_rows:
        for account_type in ("saving", "investment"):
            prefix = f"opening_{account_type}_balance_"
            if row["key"].startswith(prefix):
                name = row["key"][len(prefix):]
                if name.strip():
                    account_id = str(uuid.uuid4())
                    account_rows.append({
                        "id": account_id,
                        "user_id": row["user_id"],
                        "type": account_type,
                        "name": name,
                        "opening_balance": _opening_balance(row["value"]),
                        "is_active": True,
                    })
                    account_ids[(row["user_id"], account_type, name)] = account_id
                    migrated_setting_keys.append((row["user_id"], row["key"]))
                break
    if account_rows:
        bind.execute(accounts.insert(), account_rows)
    for user_id, key in migrated_setting_keys:
        bind.execute(
            sa.text("DELETE FROM user_settings WHERE user_id = :user_id AND key = :key"),
            {"user_id": user_id, "key": key},
        )

    # A downgrade retains the legacy type/name snapshots on transfers and assets
    # but drops accounts. Recreate the canonical pension identity from either
    # active salary contributions or those snapshots so a later zero-rate salary
    # update does not orphan historical pension references on re-upgrade.
    pension_users = bind.execute(sa.text("""
        SELECT user_id
        FROM salary_config
        WHERE employer_contrib_rate > 0 OR voluntary_contrib_rate > 0
        UNION
        SELECT user_id
        FROM transfers
        WHERE from_account_type = 'pension' OR to_account_type = 'pension'
        UNION
        SELECT user_id
        FROM assets
        WHERE asset_type = 'pension'
    """)).scalars().all()
    pension_rows = []
    for user_id in pension_users:
        account_id = str(uuid.uuid4())
        pension_rows.append({
            "id": account_id,
            "user_id": user_id,
            "type": "pension",
            "name": "Pension",
            "opening_balance": Decimal("0"),
            "is_active": True,
        })
        account_ids[(user_id, "pension", "Pension")] = account_id
    if pension_rows:
        bind.execute(accounts.insert(), pension_rows)

    bank_ids = {
        (row["user_id"], row["name"]): row["id"]
        for row in bind.execute(sa.text("""
            SELECT id, user_id, name FROM payment_methods WHERE type = 'bank'
        """)).mappings()
    }
    transfer_rows = bind.execute(sa.text("""
        SELECT id, user_id, from_account_type, from_account_name,
               to_account_type, to_account_name
        FROM transfers
    """)).mappings().all()
    for row in transfer_rows:
        values = {}
        for prefix in ("from", "to"):
            account_type = row[f"{prefix}_account_type"]
            name = row[f"{prefix}_account_name"]
            if account_type == "bank":
                payment_method_id = bank_ids.get((row["user_id"], name))
                if payment_method_id:
                    values[f"{prefix}_payment_method_id"] = payment_method_id
            else:
                account_id = (
                    account_ids.get((row["user_id"], "pension", "Pension"))
                    if account_type == "pension"
                    else account_ids.get((row["user_id"], account_type, name))
                )
                if account_id:
                    values[f"{prefix}_account_id"] = account_id
        if values:
            assignments = ", ".join(f"{column} = :{column}" for column in values)
            bind.execute(
                sa.text(f"UPDATE transfers SET {assignments} WHERE id = :id"),
                {**values, "id": row["id"]},
            )

    asset_rows = bind.execute(sa.text("""
        SELECT id, user_id, asset_type, asset_name
        FROM assets
        WHERE asset_type IN ('saving', 'investment', 'pension')
    """)).mappings().all()
    for row in asset_rows:
        account_id = (
            account_ids.get((row["user_id"], "pension", "Pension"))
            if row["asset_type"] == "pension"
            else account_ids.get((row["user_id"], row["asset_type"], row["asset_name"]))
        )
        if account_id:
            bind.execute(
                sa.text("UPDATE assets SET account_id = :account_id WHERE id = :id"),
                {"account_id": account_id, "id": row["id"]},
            )


def downgrade() -> None:
    bind = op.get_bind()

    # The legacy schema retains only name snapshots. Refresh them from valid
    # stable references before the account IDs are dropped so renamed accounts
    # can be resolved again by a later upgrade. The user/type checks prevent a
    # corrupt cross-user or cross-type reference from changing legacy history.
    for prefix in ("from", "to"):
        bind.execute(sa.text(f"""
            UPDATE transfers
            SET {prefix}_account_name = (
                SELECT name FROM accounts
                WHERE accounts.id = transfers.{prefix}_account_id
                  AND accounts.user_id = transfers.user_id
                  AND accounts.type = transfers.{prefix}_account_type
            )
            WHERE {prefix}_account_id IS NOT NULL
              AND EXISTS (
                SELECT 1 FROM accounts
                WHERE accounts.id = transfers.{prefix}_account_id
                  AND accounts.user_id = transfers.user_id
                  AND accounts.type = transfers.{prefix}_account_type
              )
        """))
    bind.execute(sa.text("""
        UPDATE assets
        SET asset_name = (
            SELECT name FROM accounts
            WHERE accounts.id = assets.account_id
              AND accounts.user_id = assets.user_id
              AND accounts.type = assets.asset_type
        )
        WHERE account_id IS NOT NULL
          AND EXISTS (
            SELECT 1 FROM accounts
            WHERE accounts.id = assets.account_id
              AND accounts.user_id = assets.user_id
              AND accounts.type = assets.asset_type
          )
    """))

    account_rows = bind.execute(
        sa.select(accounts.c.user_id, accounts.c.type, accounts.c.name, accounts.c.opening_balance)
        .where(accounts.c.type.in_(("saving", "investment")))
    ).mappings()
    for row in account_rows:
        bind.execute(
            sa.text("""
                INSERT INTO user_settings (user_id, key, value)
                VALUES (:user_id, :key, :value)
                ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value
            """),
            {
                "user_id": row["user_id"],
                "key": f"opening_{row['type']}_balance_{row['name']}",
                "value": str(_opening_balance(row["opening_balance"])),
            },
        )

    with op.batch_alter_table("assets", recreate="always") as batch_op:
        batch_op.drop_constraint("fk_assets_account_id", type_="foreignkey")
        batch_op.drop_column("account_id")
    with op.batch_alter_table("transfers", recreate="always") as batch_op:
        batch_op.drop_constraint("fk_transfers_to_account_id", type_="foreignkey")
        batch_op.drop_constraint("fk_transfers_from_account_id", type_="foreignkey")
        batch_op.drop_column("to_account_id")
        batch_op.drop_column("from_account_id")
    op.drop_index("ix_accounts_user_id", table_name="accounts")
    op.drop_table("accounts")
