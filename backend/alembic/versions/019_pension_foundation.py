"""Add pension persistence and preserve legacy contribution/balance inputs.

Revision ID: 019pension_foundation
Revises: 018remove_forecasting
"""
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
import json
import logging
import math
import uuid

from alembic import op
import sqlalchemy as sa


revision = "019pension_foundation"
down_revision = "018remove_forecasting"
branch_labels = None
depends_on = None


_MONTHLY_WEIGHTS = [1] * 12
_MONEY_QUANTUM = Decimal("0.01")
_RATE_QUANTUM = Decimal("0.0001")
_MONEY_MAX = Decimal("9999999999.99")
_RATE_MAX = Decimal("99.9999")


def _canonical_month(value: object, row_id: str, column: str) -> str:
    text = str(value)
    try:
        parsed = date.fromisoformat(text)
    except (TypeError, ValueError):
        raise RuntimeError(f"Pension migration preflight: row {row_id} has invalid {column}; remediate the date") from None
    if parsed.isoformat() != text or parsed.day != 1:
        raise RuntimeError(f"Pension migration preflight: row {row_id} has noncanonical {column}; use YYYY-MM-01")
    return text


def _decimal(value: object, row_id: str, column: str, *, rate: bool = False) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise RuntimeError(f"Pension migration preflight: row {row_id} has invalid {column}; remediate the value") from None
    quantum = _RATE_QUANTUM if rate else _MONEY_QUANTUM
    maximum = _RATE_MAX if rate else _MONEY_MAX
    try:
        representable = amount.is_finite() and amount.quantize(quantum) == amount and amount <= maximum
    except InvalidOperation:
        representable = False
    if not representable:
        raise RuntimeError(f"Pension migration preflight: row {row_id} has unrepresentable {column}; remediate the value")
    if amount < 0 or (rate and amount > 1):
        bound = "between 0 and 1" if rate else "nonnegative"
        raise RuntimeError(f"Pension migration preflight: row {row_id} has {column} outside allowed range ({bound})")
    return amount


def _legacy_rate(value: object, row_id: str, column: str) -> tuple[Decimal, bool]:
    """Preserve valid rates, canonicalizing only a one-ULP SQLite float artifact."""
    if not isinstance(value, float):
        return _decimal(value, row_id, column, rate=True), False
    if not math.isfinite(value) or value < 0 or value > 1:
        raise RuntimeError(
            f"Pension migration preflight: row {row_id} has {column} outside allowed range (0 to 1)"
        )
    amount = Decimal(str(value))
    try:
        canonical = amount.quantize(_RATE_QUANTUM)
    except InvalidOperation:
        raise RuntimeError(
            f"Pension migration preflight: row {row_id} has unrepresentable {column}; remediate the value"
        ) from None
    if amount == canonical:
        return amount, False
    canonical_float = float(canonical)
    if value == math.nextafter(canonical_float, -math.inf) or value == math.nextafter(
        canonical_float, math.inf
    ):
        return canonical, True
    raise RuntimeError(
        f"Pension migration preflight: row {row_id} has unrepresentable {column}; remediate the value"
    )


def _preflight(bind):
    """Validate all source data and calculate deterministic backfill rows before DDL."""
    users = set(bind.execute(sa.text("SELECT id FROM users")).scalars())
    account_rows = bind.execute(sa.text("""
        SELECT id, user_id, type, name, opening_balance, is_active
        FROM accounts
        WHERE type = 'pension'
    """)).mappings().all()
    accounts_by_user = defaultdict(list)
    account_by_id = {}
    for account in account_rows:
        if account["user_id"] not in users:
            raise RuntimeError(f"Pension migration preflight: pension account {account['id']} has no owner")
        _decimal(account["opening_balance"], account["id"], "opening_balance")
        if Decimal(str(account["opening_balance"])) != 0:
            raise RuntimeError(
                f"Pension migration preflight: pension account {account['id']} has a nonzero undated opening balance; confirm its opening month before retrying"
            )
        accounts_by_user[account["user_id"]].append(dict(account))
        account_by_id[account["id"]] = dict(account)

    salary_rows = bind.execute(sa.text("""
        SELECT id, user_id, valid_from, ral, voluntary_contrib_rate, employer_contrib_rate
        FROM salary_config
        ORDER BY user_id, valid_from, id
    """)).mappings().all()
    salary_inputs = defaultdict(list)
    canonicalized_rate_count = 0
    for row in salary_rows:
        if row["user_id"] not in users:
            raise RuntimeError(f"Pension migration preflight: salary row {row['id']} has no owner")
        valid_from = _canonical_month(row["valid_from"], row["id"], "valid_from")
        ral = _decimal(row["ral"], row["id"], "ral")
        employee_rate, normalized_employee = _legacy_rate(
            row["voluntary_contrib_rate"], row["id"], "voluntary_contrib_rate"
        )
        employer_rate, normalized_employer = _legacy_rate(
            row["employer_contrib_rate"], row["id"], "employer_contrib_rate"
        )
        canonicalized_rate_count += int(normalized_employee) + int(normalized_employer)
        salary_inputs[row["user_id"]].append({
            "id": row["id"],
            "user_id": row["user_id"],
            "valid_from": valid_from,
            "employee_contrib_rate": employee_rate,
            "employee_contrib_annual_base": ral,
            "employer_contrib_rate": employer_rate,
            "employer_contrib_annual_base": ral,
        })

    coalesced_salary = {}
    histories = defaultdict(list)
    for user_id, rows in salary_inputs.items():
        periods = defaultdict(list)
        for row in rows:
            periods[row["valid_from"]].append(row)
        for valid_from, duplicates in periods.items():
            mapped = {
                (row["employee_contrib_rate"], row["employee_contrib_annual_base"],
                 row["employer_contrib_rate"], row["employer_contrib_annual_base"])
                for row in duplicates
            }
            if len(mapped) != 1:
                ids = ", ".join(sorted(row["id"] for row in duplicates))
                raise RuntimeError(
                    f"Pension migration preflight: conflicting salary rows {ids} share effective month {valid_from}; resolve the duplicate period"
                )
            chosen = min(duplicates, key=lambda row: row["id"])
            coalesced_salary[(user_id, valid_from)] = chosen
        histories[user_id] = [coalesced_salary[(user_id, period)] for period in sorted(periods)]

    contribution_users = {
        user_id for user_id, rows in histories.items()
        if any(row["employee_contrib_rate"] > 0 or row["employer_contrib_rate"] > 0 for row in rows)
    }
    config_accounts = {}
    created_accounts = []
    for user_id in sorted(contribution_users):
        owned = accounts_by_user[user_id]
        if len(owned) > 1:
            raise RuntimeError(
                f"Pension migration preflight: user {user_id} has multiple pension accounts for legacy contributions; choose the destination account"
            )
        if owned:
            config_accounts[user_id] = owned[0]["id"]
        else:
            account_id = str(uuid.uuid4())
            config_accounts[user_id] = account_id
            created_accounts.append({
                "id": account_id,
                "user_id": user_id,
                "type": "pension",
                "name": "Pension",
                "opening_balance": Decimal("0.00"),
                "is_active": True,
            })

    assets = bind.execute(sa.text("""
        SELECT id, user_id, year, asset_type, account_id, manual_override, notes
        FROM assets
        WHERE asset_type = 'pension' AND manual_override IS NOT NULL
        ORDER BY id
    """)).mappings().all()
    overrides = []
    override_values = {}
    for asset in assets:
        if asset["user_id"] not in users:
            raise RuntimeError(f"Pension migration preflight: pension override {asset['id']} has no owner")
        try:
            year = int(asset["year"])
        except (TypeError, ValueError):
            raise RuntimeError(f"Pension migration preflight: pension override {asset['id']} has invalid year") from None
        if year < 1 or year > 9999 or str(year) != str(asset["year"]):
            raise RuntimeError(f"Pension migration preflight: pension override {asset['id']} has invalid year")
        balance = _decimal(asset["manual_override"], asset["id"], "manual_override")
        owner_accounts = accounts_by_user[asset["user_id"]]
        if asset["account_id"]:
            account = account_by_id.get(asset["account_id"])
            if account is None or account["user_id"] != asset["user_id"]:
                raise RuntimeError(
                    f"Pension migration preflight: pension override {asset['id']} references an unmatched or foreign-owned account; resolve the stable account reference"
                )
        elif len(owner_accounts) == 1:
            account = owner_accounts[0]
        elif len(owner_accounts) == 0:
            raise RuntimeError(
                f"Pension migration preflight: pension override {asset['id']} has no owned pension account; resolve its destination"
            )
        else:
            raise RuntimeError(
                f"Pension migration preflight: pension override {asset['id']} has ambiguous pension accounts; resolve its destination"
            )
        snapshot_month = f"{year:04d}-12-01"
        key = (asset["user_id"], account["id"], snapshot_month)
        signature = (balance, asset["notes"])
        first_override = override_values.get(key)
        if first_override and first_override["signature"] != signature:
            raise RuntimeError(
                f"Pension migration preflight: conflicting legacy overrides "
                f"{first_override['row_id']} and {asset['id']} target {snapshot_month}; "
                "resolve the duplicate snapshot"
            )
        override_values.setdefault(key, {"signature": signature, "row_id": asset["id"]})
        overrides.append({
            "id": asset["id"], "user_id": asset["user_id"], "account_id": account["id"],
            "as_of_month": snapshot_month, "balance": balance, "notes": asset["notes"],
        })

    all_accounts = accounts_by_user
    for account in created_accounts:
        all_accounts[account["user_id"]].append(account)
    transfers = bind.execute(sa.text("""
        SELECT id, user_id, date, from_account_type, from_account_id,
               to_account_type, to_account_id
        FROM transfers
        WHERE from_account_type = 'pension' OR to_account_type = 'pension'
    """)).mappings().all()
    transfer_months = defaultdict(list)
    for transfer in transfers:
        for prefix in ("from", "to"):
            if transfer[f"{prefix}_account_type"] != "pension":
                continue
            account_id = transfer[f"{prefix}_account_id"]
            if not account_id:
                raise RuntimeError(
                    f"Pension migration preflight: transfer {transfer['id']} has a pension {prefix} endpoint without a stable account ID; resolve the historical account reference"
                )
            account = account_by_id.get(account_id)
            if account is None or account["user_id"] != transfer["user_id"]:
                raise RuntimeError(
                    f"Pension migration preflight: transfer {transfer['id']} has an unmatched or foreign pension account reference"
                )
            transfer_date = str(transfer["date"])
            try:
                parsed_transfer_date = date.fromisoformat(transfer_date)
            except (TypeError, ValueError):
                raise RuntimeError(
                    f"Pension migration preflight: transfer {transfer['id']} has an invalid date; remediate the date"
                ) from None
            transfer_months[account["id"]].append(
                f"{parsed_transfer_date.year:04d}-{parsed_transfer_date.month:02d}-01"
            )

    settings = bind.execute(sa.text("""
        SELECT user_id, value FROM user_settings WHERE key = 'tracking_start_date'
    """)).mappings().all()
    tracking_by_user = {row["user_id"]: row["value"] for row in settings}

    opening_months = {}
    for user_id, owned in all_accounts.items():
        for account in owned:
            account_id = account["id"]
            dates = list(transfer_months[account_id])
            dates.extend(row["valid_from"] for row in histories.get(user_id, [])
                         if config_accounts.get(user_id) == account_id and user_id in contribution_users)
            dates.extend(row["as_of_month"] for row in overrides if row["account_id"] == account_id)
            if dates:
                opening_months[account_id] = min(dates)
            else:
                tracking = tracking_by_user.get(user_id)
                if tracking is None:
                    raise RuntimeError(
                        f"Pension migration preflight: pension account {account_id} has no dated history or tracking_start_date; provide a valid tracking month"
                    )
                opening_months[account_id] = _canonical_month(tracking, user_id, "tracking_start_date")

    configs = []
    for user_id in sorted(contribution_users):
        account_id = config_accounts[user_id]
        for row in histories[user_id]:
            configs.append({
                "id": row["id"], "user_id": user_id, "account_id": account_id,
                "valid_from": row["valid_from"],
                "employee_contrib_rate": row["employee_contrib_rate"],
                "employee_contrib_annual_base": row["employee_contrib_annual_base"],
                "employer_contrib_rate": row["employer_contrib_rate"],
                "employer_contrib_annual_base": row["employer_contrib_annual_base"],
                "tfr_contrib_annual": Decimal("0.00"),
                "contribution_periods_by_month": _MONTHLY_WEIGHTS,
            })

    snapshots = {}
    for row in overrides:
        key = (row["user_id"], row["account_id"], row["as_of_month"])
        snapshots.setdefault(key, {
            "id": row["id"], "user_id": row["user_id"], "account_id": row["account_id"],
            "as_of_month": row["as_of_month"], "balance": row["balance"],
            "source": "legacy_override", "notes": row["notes"],
        })
    return created_accounts, opening_months, configs, list(snapshots.values()), canonicalized_rate_count


def upgrade() -> None:
    bind = op.get_bind()
    created_accounts, opening_months, configs, snapshots, canonicalized_rate_count = _preflight(bind)
    logging.getLogger("alembic.runtime.migration").info(
        "Pension legacy rate canonicalizations within one float ULP: %s",
        canonicalized_rate_count,
    )

    op.add_column("accounts", sa.Column("opening_balance_month", sa.String(10), nullable=True))
    op.create_index("uq_accounts_user_id_id", "accounts", ["user_id", "id"], unique=True)
    op.create_table(
        "pension_configs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("account_id", sa.String(36), nullable=False),
        sa.Column("valid_from", sa.String(10), nullable=False),
        sa.Column("employee_contrib_rate", sa.Numeric(6, 4), nullable=False),
        sa.Column("employee_contrib_annual_base", sa.Numeric(12, 2), nullable=False),
        sa.Column("employer_contrib_rate", sa.Numeric(6, 4), nullable=False),
        sa.Column("employer_contrib_annual_base", sa.Numeric(12, 2), nullable=False),
        sa.Column("tfr_contrib_annual", sa.Numeric(12, 2), nullable=False),
        sa.Column("contribution_periods_by_month", sa.JSON(), nullable=False),
        sa.UniqueConstraint("user_id", "valid_from", name="uq_pension_config_user_valid_from"),
        sa.ForeignKeyConstraint(
            ["user_id", "account_id"], ["accounts.user_id", "accounts.id"],
            name="fk_pension_config_owned_account", ondelete="CASCADE",
        ),
        sa.CheckConstraint("employee_contrib_rate >= 0 AND employee_contrib_rate <= 1", name="ck_pension_config_employee_rate"),
        sa.CheckConstraint("employer_contrib_rate >= 0 AND employer_contrib_rate <= 1", name="ck_pension_config_employer_rate"),
        sa.CheckConstraint("employee_contrib_annual_base >= 0", name="ck_pension_config_employee_base"),
        sa.CheckConstraint("employer_contrib_annual_base >= 0", name="ck_pension_config_employer_base"),
        sa.CheckConstraint("tfr_contrib_annual >= 0", name="ck_pension_config_tfr"),
    )
    op.create_index("ix_pension_configs_user_id", "pension_configs", ["user_id"])
    op.create_table(
        "pension_balance_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("account_id", sa.String(36), nullable=False),
        sa.Column("as_of_month", sa.String(10), nullable=False),
        sa.Column("balance", sa.Numeric(12, 2), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.UniqueConstraint("user_id", "account_id", "as_of_month", name="uq_pension_snapshot_user_account_month"),
        sa.ForeignKeyConstraint(
            ["user_id", "account_id"], ["accounts.user_id", "accounts.id"],
            name="fk_pension_snapshot_owned_account", ondelete="CASCADE",
        ),
        sa.CheckConstraint("balance >= 0", name="ck_pension_snapshot_balance"),
        sa.CheckConstraint("source IN ('statement', 'manual', 'legacy_override')", name="ck_pension_snapshot_source"),
    )
    op.create_index("ix_pension_balance_snapshots_user_id", "pension_balance_snapshots", ["user_id"])

    if created_accounts:
        bind.execute(sa.text("""
            INSERT INTO accounts (id, user_id, type, name, opening_balance, is_active)
            VALUES (:id, :user_id, :type, :name, :opening_balance, :is_active)
        """), [{**row, "opening_balance": str(row["opening_balance"])} for row in created_accounts])
    for account_id, opening_month in opening_months.items():
        bind.execute(sa.text("""
            UPDATE accounts SET opening_balance_month = :opening_month WHERE id = :account_id
        """), {"account_id": account_id, "opening_month": opening_month})
    if configs:
        bind.execute(sa.text("""
            INSERT INTO pension_configs
                (id, user_id, account_id, valid_from, employee_contrib_rate,
                 employee_contrib_annual_base, employer_contrib_rate,
                 employer_contrib_annual_base, tfr_contrib_annual,
                 contribution_periods_by_month)
            VALUES
                (:id, :user_id, :account_id, :valid_from, :employee_contrib_rate,
                 :employee_contrib_annual_base, :employer_contrib_rate,
                 :employer_contrib_annual_base, :tfr_contrib_annual,
                 :contribution_periods_by_month)
        """), [{
            **row,
            "employee_contrib_rate": str(row["employee_contrib_rate"]),
            "employee_contrib_annual_base": str(row["employee_contrib_annual_base"]),
            "employer_contrib_rate": str(row["employer_contrib_rate"]),
            "employer_contrib_annual_base": str(row["employer_contrib_annual_base"]),
            "tfr_contrib_annual": str(row["tfr_contrib_annual"]),
            "contribution_periods_by_month": json.dumps(row["contribution_periods_by_month"]),
        } for row in configs])
    if snapshots:
        bind.execute(sa.text("""
            INSERT INTO pension_balance_snapshots
                (id, user_id, account_id, as_of_month, balance, source, notes)
            VALUES (:id, :user_id, :account_id, :as_of_month, :balance, :source, :notes)
        """), [{**row, "balance": str(row["balance"])} for row in snapshots])


def downgrade() -> None:
    raise RuntimeError("Pension data cannot be safely downgraded; restore a pre-upgrade database backup")
