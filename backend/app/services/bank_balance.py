import bisect
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy.orm import Session
from app.models.payment_method import CardBankLinkHistory, MainBankHistory, PaymentMethod
from app.models.transaction import Transaction
from app.models.transfer import Transfer
from app.services.billing import BANK_FUNDED_CARD_TYPES
from app.services.transaction_semantics import transaction_semantics

_CENTS = Decimal("0.01")


def _bulk_load(user_id: str, start_month_first: str, end_date: str, db: Session):
    """Bulk-load every dataset needed to walk the rolling bank balance.

    Returns a tuple ``(mbh_rows, mbh_dates, pm_by_id, card_links_by_card,
    txs_by_month, transfers_by_month)``:
    - ``mbh_rows``: MainBankHistory rows for the user, ordered by ``valid_from`` asc
    - ``mbh_dates``: parallel list of ``valid_from`` strings for O(log n) bisect lookup
    - ``pm_by_id``: ``{payment_method_id: PaymentMethod}``
    - ``card_links_by_card``: effective card-bank links ordered by billing period
    - ``txs_by_month``: ``{billing_month: [Transaction, ...]}``
    - ``transfers_by_month``: ``{billing_month: [Transfer, ...]}``
    """
    mbh_rows = (
        db.query(MainBankHistory)
        .filter_by(user_id=user_id)
        .order_by(MainBankHistory.valid_from.asc())
        .all()
    )
    pm_by_id: dict[str, PaymentMethod] = {
        pm.id: pm
        for pm in db.query(PaymentMethod).filter_by(user_id=user_id).all()
    }
    card_links_by_card: dict[str, list[CardBankLinkHistory]] = defaultdict(list)
    for link in (
        db.query(CardBankLinkHistory)
        .filter_by(user_id=user_id)
        .order_by(CardBankLinkHistory.card_payment_method_id, CardBankLinkHistory.valid_from)
        .all()
    ):
        card_links_by_card[link.card_payment_method_id].append(link)

    all_txs = (
        db.query(Transaction)
        .filter(
            Transaction.user_id == user_id,
            Transaction.billing_month >= start_month_first,
            Transaction.billing_month <= end_date,
        )
        .all()
    )
    txs_by_month: dict[str, list[Transaction]] = defaultdict(list)
    for tx in all_txs:
        txs_by_month[tx.billing_month].append(tx)

    all_transfers = (
        db.query(Transfer)
        .filter(
            Transfer.user_id == user_id,
            Transfer.billing_month >= start_month_first,
            Transfer.billing_month <= end_date,
        )
        .all()
    )
    transfers_by_month: dict[str, list[Transfer]] = defaultdict(list)
    for t in all_transfers:
        transfers_by_month[t.billing_month].append(t)

    mbh_dates = [_month_start(row.valid_from) for row in mbh_rows]
    return mbh_rows, mbh_dates, pm_by_id, card_links_by_card, txs_by_month, transfers_by_month


def _accumulate_balances(
    mbh_rows: list,
    mbh_dates: list[str],
    pm_by_id: dict,
    card_links_by_card: dict,
    txs_by_month: dict,
    transfers_by_month: dict,
    start_year: int,
    start_month: int,
    until_year: int,
    until_month: int,
) -> dict[str, float]:
    """Walk month-by-month from (start_year, start_month) through (until_year, until_month),
    applying the main bank's opening balance, transactions, and transfers. Returns a dict
    keyed by ``'YYYY-MM-01'`` month-first string to the end-of-month rolling balance.
    """
    result: dict[str, float] = {}
    # Accumulate in Decimal so cent-drift never builds up across the month walk.
    # Only the public result dict is converted back to float.
    balance = Decimal("0")
    active_history_index: int | None = None
    curr_year, curr_month = start_year, start_month

    while (curr_year, curr_month) <= (until_year, until_month):
        month_first = f"{curr_year:04d}-{curr_month:02d}-01"

        # Binary search: rightmost MBH row with valid_from <= month_first
        idx = bisect.bisect_right(mbh_dates, month_first) - 1
        mbh = mbh_rows[idx] if idx >= 0 else None

        if mbh:
            # Initialize when the first applicable history row becomes active.  Legacy
            # rows may have mid-month dates, which take effect for that whole month.
            if idx != active_history_index:
                balance = Decimal(str(mbh.opening_balance))
                active_history_index = idx

            pm = pm_by_id.get(mbh.payment_method_id)
            if pm:
                # Apply transactions for this billing month using the shared
                # payment-method/direction matrix.  Unsupported legacy rows have no
                # impact because the API can no longer create them.
                for tx in txs_by_month.get(month_first, []):
                    tx_pm = pm_by_id.get(tx.payment_method_id)
                    if tx.payment_method_id == pm.id:
                        semantics = transaction_semantics(pm.type, tx.transaction_direction)
                    elif (
                        tx_pm
                        and tx_pm.type in BANK_FUNDED_CARD_TYPES
                        and _linked_bank_for_billing_month(
                            tx_pm, tx.billing_month, card_links_by_card
                        ) == pm.id
                    ):
                        # Bank-funded cards affect the bank linked for this transaction's
                        # billing month, never whichever bank the card links to today.
                        semantics = transaction_semantics(tx_pm.type, tx.transaction_direction)
                    else:
                        semantics = None

                    if semantics:
                        balance += Decimal(str(tx.amount)) * semantics.bank_balance_delta

                # Apply transfers for this billing month — prefer the stable FK id
                # when available, fall back to name matching for legacy rows that
                # predate the 008 migration / FK backfill.
                for t in transfers_by_month.get(month_first, []):
                    from_match = (
                        (t.from_payment_method_id is not None and t.from_payment_method_id == pm.id)
                        or (
                            t.from_payment_method_id is None
                            and t.from_account_type == "bank"
                            and t.from_account_name == pm.name
                        )
                    )
                    to_match = (
                        (t.to_payment_method_id is not None and t.to_payment_method_id == pm.id)
                        or (
                            t.to_payment_method_id is None
                            and t.to_account_type == "bank"
                            and t.to_account_name == pm.name
                        )
                    )
                    if from_match:
                        balance -= Decimal(str(t.amount))
                    elif to_match:
                        balance += Decimal(str(t.amount))

        result[month_first] = float(balance.quantize(_CENTS, rounding=ROUND_HALF_UP))
        curr_year, curr_month = _advance_month(curr_year, curr_month)

    return result


def compute_bank_balance(
    user_id: str,
    year: int,
    month: int,
    db: Session,
    *,
    _preloaded: dict | None = None,
) -> float:
    """
    Compute rolling bank balance for the given year/month.
    Starts from tracking_start_date's main bank opening_balance and applies
    income/debit transactions and transfers month by month up to and including
    the requested month.

    When ``_preloaded`` is provided (a dict with keys ``mbh_rows``, ``mbh_dates``,
    ``pm_by_id``, ``txs_by_month``, ``transfers_by_month``, ``start_year``,
    ``start_month``), the bulk queries are skipped and the supplied data is used —
    this lets callers such as :func:`app.services.summary.monthly_summary` load the
    datasets once and reuse them.
    """
    from app.models.user import UserSetting

    if _preloaded is not None:
        start_year = _preloaded["start_year"]
        start_month = _preloaded["start_month"]
        mbh_rows = _preloaded["mbh_rows"]
        mbh_dates = _preloaded["mbh_dates"]
        pm_by_id = _preloaded["pm_by_id"]
        card_links_by_card = _preloaded["card_links_by_card"]
        txs_by_month = _preloaded["txs_by_month"]
        transfers_by_month = _preloaded["transfers_by_month"]
    else:
        start_setting = db.query(UserSetting).filter_by(user_id=user_id, key="tracking_start_date").first()
        if not start_setting:
            return 0.0
        start_parts = start_setting.value.split("-")
        start_year, start_month = int(start_parts[0]), int(start_parts[1])

        start_month_first = f"{start_year:04d}-{start_month:02d}-01"
        end_date = f"{year:04d}-{month:02d}-01"
        mbh_rows, mbh_dates, pm_by_id, card_links_by_card, txs_by_month, transfers_by_month = _bulk_load(
            user_id, start_month_first, end_date, db
        )

    if not mbh_rows:
        return 0.0

    balances = _accumulate_balances(
        mbh_rows, mbh_dates, pm_by_id, card_links_by_card, txs_by_month, transfers_by_month,
        start_year, start_month, year, month,
    )

    target_key = f"{year:04d}-{month:02d}-01"
    return balances.get(target_key, 0.0)


def compute_bank_balances_for_year(user_id: str, year: int, db: Session) -> dict[int, float]:
    """
    Compute the bank balance at end of each month for a full year in a single pass.
    Does the same 4 bulk loads as compute_bank_balance but only once, then accumulates
    from tracking_start through December, capturing the balance at each month boundary.
    Returns {1: balance, 2: balance, ..., 12: balance}.
    """
    from app.models.user import UserSetting
    start_setting = db.query(UserSetting).filter_by(user_id=user_id, key="tracking_start_date").first()
    if not start_setting:
        return {m: 0.0 for m in range(1, 13)}
    start_parts = start_setting.value.split("-")
    start_year, start_month = int(start_parts[0]), int(start_parts[1])

    start_month_first = f"{start_year:04d}-{start_month:02d}-01"
    end_date = f"{year:04d}-12-01"

    mbh_rows, mbh_dates, pm_by_id, card_links_by_card, txs_by_month, transfers_by_month = _bulk_load(
        user_id, start_month_first, end_date, db
    )

    balances = _accumulate_balances(
        mbh_rows, mbh_dates, pm_by_id, card_links_by_card, txs_by_month, transfers_by_month,
        start_year, start_month, year, 12,
    )

    result: dict[int, float] = {}
    for m in range(1, 13):
        key = f"{year:04d}-{m:02d}-01"
        result[m] = balances.get(key, 0.0)
    return result


def _linked_bank_for_billing_month(
    card: PaymentMethod,
    billing_month: str,
    card_links_by_card: dict[str, list[CardBankLinkHistory]],
) -> str | None:
    links = card_links_by_card.get(card.id, [])
    if links:
        effective_dates = [link.valid_from for link in links]
        index = bisect.bisect_right(effective_dates, billing_month) - 1
        return links[index].linked_bank_id if index >= 0 else None
    # Fallback only supports legacy rows that predate the migration. API-created
    # cards always have a history row, so no current link can rewrite their past.
    return card.linked_bank_id


def _month_start(value: str) -> str:
    year, month, _ = value.split("-", 2)
    return f"{int(year):04d}-{int(month):02d}-01"


def _advance_month(year: int, month: int):
    if month == 12:
        return year + 1, 1
    return year, month + 1
