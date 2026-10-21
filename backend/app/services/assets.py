from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, List
from sqlalchemy.orm import Session
from dateutil.parser import parse as _p
from dateutil.relativedelta import relativedelta as _rdelta

from app.models.account import Account
from app.models.asset import Asset
from app.models.transfer import Transfer
from app.models.user import UserSetting
from app.services.pension import pension_balances


@dataclass
class AssetRow:
    asset_type: str          # saving | investment | bank | pension
    asset_name: str
    computed_amount: float
    manual_override: Optional[float]
    final_amount: float
    account_id: Optional[str] = None
    valuation_status: Optional[str] = None
    reconciled_as_of_month: Optional[str] = None
    reconciled_balance: Optional[float] = None
    reconciliation_source: Optional[str] = None
    employee_contributions: Optional[float] = None
    employer_contributions: Optional[float] = None
    tfr_contributions: Optional[float] = None
    net_transfers: Optional[float] = None
    projected_through: Optional[str] = None


def _legacy_accounts(db: Session, user_id: str) -> list[tuple[str, str, Decimal]]:
    """Read only pre-015 opening-balance keys when no stable row exists.

    The migration consumes these keys. This fallback intentionally does not
    create accounts and only recognizes the two historical key prefixes.
    """
    rows = db.query(UserSetting).filter_by(user_id=user_id).all()
    result = []
    for row in rows:
        for account_type in ("saving", "investment"):
            prefix = f"opening_{account_type}_balance_"
            if row.key.startswith(prefix) and row.key[len(prefix):].strip():
                result.append((account_type, row.key[len(prefix):], Decimal(row.value)))
    return result


def compute_assets(
    user_id: str, year: int, db: Session, as_of: Optional[str] = None
) -> List[AssetRow]:
    """Calculate assets through an inclusive first-of-month reporting cutoff.

    Service callers that do not specify a cutoff retain the historical annual
    snapshot behavior by using December as the cutoff.
    """
    as_of = as_of or f"{year:04d}-12-01"
    accounts = (
        db.query(Account)
        .filter(Account.user_id == user_id, Account.is_active.is_(True))
        .order_by(Account.type, Account.name)
        .all()
    )
    accounts_by_id = {account.id: account for account in accounts}
    accounts_by_name = {(account.type, account.name): account for account in accounts}

    # Manual overrides for this year use stable account IDs. Name matching is
    # retained only for rows created before the migration and only while a
    # currently owned account has that exact legacy name.
    overrides_by_id = {
        asset.account_id: asset.manual_override
        for asset in db.query(Asset).filter_by(user_id=user_id, year=year).all()
        if asset.account_id is not None
    }
    legacy_overrides = {
        (asset.asset_type, asset.asset_name): asset.manual_override
        for asset in db.query(Asset).filter_by(user_id=user_id, year=year).all()
        if asset.account_id is None
    }

    rows: List[AssetRow] = []

    def _make_row(account: Account | None, asset_type: str, name: str, computed: float):
        account_id = account.id if account is not None else None
        if asset_type == "pension":
            override = None
        elif account_id is not None and account_id in overrides_by_id:
            # A stable row is authoritative even when its null override clears
            # a previously migrated name-based override.
            override = overrides_by_id[account_id]
        else:
            override = legacy_overrides.get((asset_type, name))
        return AssetRow(
            asset_type=asset_type, asset_name=name, account_id=account_id,
            computed_amount=computed,
            manual_override=override,
            final_amount=override if override is not None else computed,
        )

    # Bulk-load all transfers through this inclusive month once (cumulative
    # balance: transfers from earlier years carry forward).
    year_transfers = (
        db.query(Transfer)
        .filter_by(user_id=user_id)
        .filter(Transfer.billing_month <= as_of)
        .all()
    )
    transfers_in: dict[str, Decimal] = defaultdict(Decimal)
    transfers_out: dict[str, Decimal] = defaultdict(Decimal)
    for transfer in year_transfers:
        # Old rows lacking an ID may still be read only if their name resolves
        # to an active owned row. Unknown/stale names cannot become assets.
        from_id = transfer.from_account_id
        if from_id is None:
            legacy = accounts_by_name.get((transfer.from_account_type, transfer.from_account_name))
            from_id = legacy.id if legacy else None
        to_id = transfer.to_account_id
        if to_id is None:
            legacy = accounts_by_name.get((transfer.to_account_type, transfer.to_account_name))
            to_id = legacy.id if legacy else None
        if to_id in accounts_by_id:
            transfers_in[to_id] += Decimal(transfer.amount)
        if from_id in accounts_by_id:
            transfers_out[from_id] += Decimal(transfer.amount)

    def _transfer_balance(opening: Decimal, account_id: str) -> float:
        return float(opening + transfers_in[account_id] - transfers_out[account_id])

    for account in accounts:
        if account.type in {"saving", "investment"}:
            rows.append(_make_row(
                account, account.type, account.name,
                _transfer_balance(Decimal(account.opening_balance), account.id),
            ))

    # Standalone/test databases representing an unmigrated installation retain
    # the exact historical settings shape without inventing a persistent ID.
    if not accounts:
        for account_type, name, opening_balance in _legacy_accounts(db, user_id):
            legacy_in = sum(
                (Decimal(transfer.amount) for transfer in year_transfers
                 if transfer.to_account_type == account_type and transfer.to_account_name == name),
                Decimal(),
            )
            legacy_out = sum(
                (Decimal(transfer.amount) for transfer in year_transfers
                 if transfer.from_account_type == account_type and transfer.from_account_name == name),
                Decimal(),
            )
            rows.append(_make_row(None, account_type, name, float(opening_balance + legacy_in - legacy_out)))

    # Pension balances use the shared cumulative calculation, independent of name/year.
    for balance in pension_balances(db, user_id, as_of):
        account = accounts_by_id.get(balance.account_id)
        if account is None:
            continue
        rows.append(AssetRow(
            asset_type="pension", asset_name=balance.account_name,
            account_id=balance.account_id, computed_amount=float(balance.balance),
            manual_override=None, final_amount=float(balance.balance),
            valuation_status=balance.valuation_status,
            reconciled_as_of_month=balance.reconciled_as_of_month,
            reconciled_balance=float(balance.reconciled_balance) if balance.reconciled_balance is not None else None,
            reconciliation_source=balance.reconciliation_source,
            employee_contributions=float(balance.employee_contributions),
            employer_contributions=float(balance.employer_contributions),
            tfr_contributions=float(balance.tfr_contributions),
            net_transfers=float(balance.net_transfers),
            projected_through=balance.projected_through,
        ))

    return rows
