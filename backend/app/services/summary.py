from decimal import Decimal

from sqlalchemy.orm import Session
from app.models.transaction import Transaction
from app.models.transfer import Transfer
from app.models.payment_method import PaymentMethod
from app.models.user import UserSetting
from app.services.bank_balance import (
    compute_bank_balance,
    compute_bank_balances_for_year,
    _bulk_load,
)
from app.services.transaction_semantics import transaction_semantics


_STAMP_DUTY_THRESHOLD = 77.47
_STAMP_DUTY_AMOUNT = 2.00


def _compute_stamp_duty(month_first: str, all_txs: list[Transaction], stamp_duty_cards: list[PaymentMethod]) -> float:
    """
    Compute the Italian imposta di bollo for a given month.

    Only credit cards with has_stamp_duty=True are eligible (passed as stamp_duty_cards).
    If a card's debit spend for the month exceeds €77.47, add €2.00 per card.

    Accepts a pre-loaded list of stamp_duty_cards (PaymentMethod rows) and a
    pre-filtered list of transactions for the month to avoid per-call DB queries.
    The caller is responsible for loading and filtering them.
    """
    if not stamp_duty_cards:
        return 0.0

    total = 0.0
    for pm in stamp_duty_cards:
        monthly_spend = sum(
            float(tx.amount)
            for tx in all_txs
            if tx.payment_method_id == pm.id
            and tx.billing_month == month_first
            and tx.transaction_direction == "debit"
        )
        if monthly_spend > _STAMP_DUTY_THRESHOLD:
            total += _STAMP_DUTY_AMOUNT

    return total


def _transaction_summary_totals(
    transactions: list[Transaction], payment_methods: dict[str, PaymentMethod]
) -> tuple[float, dict[str, float]]:
    """Aggregate incomes and signed net outcomes from the shared direction matrix."""
    income = Decimal("0")
    outcomes: dict[str, Decimal] = {}
    for tx in transactions:
        payment_method = payment_methods.get(tx.payment_method_id)
        if not payment_method:
            continue
        semantics = transaction_semantics(payment_method.type, tx.transaction_direction)
        if not semantics:
            continue
        amount = Decimal(str(tx.amount))
        income += amount * semantics.income_delta
        if semantics.outcome_delta:
            name = payment_method.name
            outcomes[name] = outcomes.get(name, Decimal("0")) + amount * semantics.outcome_delta

    return float(income), {name: float(amount) for name, amount in outcomes.items()}


def monthly_summary(user_id: str, year: int, month: int, db: Session) -> dict:
    """Build the single-month summary payload.

    Previously this function re-queried the month's transactions, transfers, and
    payment-method names even though ``compute_bank_balance`` already bulk-loaded
    the same data to compute the rolling balance. We now load everything once via
    :func:`_bulk_load` and share it with ``compute_bank_balance`` via its
    ``_preloaded`` hook — eliminating the duplicate queries per dashboard load.
    """
    month_first = f"{year:04d}-{month:02d}-01"

    # Resolve tracking_start once — if unset, behave exactly like the unoptimised
    # path: no bank-balance computation, no bulk load, still compute the month's
    # own aggregates (which will all be zero without data anyway).
    start_setting = db.query(UserSetting).filter_by(user_id=user_id, key="tracking_start_date").first()

    if start_setting:
        start_parts = start_setting.value.split("-")
        start_year, start_month = int(start_parts[0]), int(start_parts[1])
        start_month_first = f"{start_year:04d}-{start_month:02d}-01"

        mbh_rows, mbh_dates, pm_by_id, card_links_by_card, txs_by_month, transfers_by_month = _bulk_load(
            user_id, start_month_first, month_first, db
        )

        bank_balance = compute_bank_balance(
            user_id, year, month, db,
            _preloaded={
                "start_year": start_year,
                "start_month": start_month,
                "mbh_rows": mbh_rows,
                "mbh_dates": mbh_dates,
                "pm_by_id": pm_by_id,
                "card_links_by_card": card_links_by_card,
                "txs_by_month": txs_by_month,
                "transfers_by_month": transfers_by_month,
            },
        )
        txs = txs_by_month.get(month_first, [])
        transfers = transfers_by_month.get(month_first, [])
    else:
        # No tracking_start → compute_bank_balance returns 0.0; still produce
        # the month aggregates from the DB (there is no cached data to reuse).
        bank_balance = 0.0
        pm_by_id = {
            pm.id: pm
            for pm in db.query(PaymentMethod).filter_by(user_id=user_id).all()
        }
        txs = db.query(Transaction).filter_by(user_id=user_id).filter(
            Transaction.billing_month == month_first
        ).all()
        transfers = db.query(Transfer).filter_by(user_id=user_id).filter(
            Transfer.billing_month == month_first
        ).all()

    total_income, by_method = _transaction_summary_totals(txs, pm_by_id)

    transfers_out = sum(float(t.amount) for t in transfers if t.from_account_type == "bank")
    transfers_in = sum(float(t.amount) for t in transfers if t.to_account_type == "bank")

    # Stamp-duty cards are a separate concern (filter on has_stamp_duty) and are
    # usually a very small set; keep this as a dedicated query.
    stamp_duty_cards = [pm for pm in pm_by_id.values() if pm.type == "credit_card" and pm.has_stamp_duty] \
        if start_setting else (
            db.query(PaymentMethod)
            .filter_by(user_id=user_id, type="credit_card", has_stamp_duty=True)
            .all()
        )
    stamp_duty = _compute_stamp_duty(month_first, txs, stamp_duty_cards)

    return {
        "year": year,
        "month": month,
        "incomes": total_income,
        "outcomes_by_method": by_method,
        "transfers_out_bank": transfers_out,
        "transfers_in_bank": transfers_in,
        "bank_balance": bank_balance,
        "stamp_duty": stamp_duty,
    }


def year_monthly_summaries(user_id: str, year: int, db: Session) -> list[dict]:
    """
    Compute all 12 monthly summaries for a year in a single pass.
    Uses compute_bank_balances_for_year to avoid re-loading all history 12 times.
    Total DB queries: ~7 regardless of history length (vs 72 with 12x monthly_summary calls).
    """
    year_prefix = f"{year:04d}-"

    all_txs = (
        db.query(Transaction)
        .filter_by(user_id=user_id)
        .filter(Transaction.billing_month.startswith(year_prefix))
        .all()
    )
    txs_by_month: dict[int, list[Transaction]] = {m: [] for m in range(1, 13)}
    for tx in all_txs:
        m = int(tx.billing_month[5:7])
        txs_by_month[m].append(tx)

    pm_ids = {tx.payment_method_id for tx in all_txs}
    pm_by_id: dict[str, PaymentMethod] = {}
    if pm_ids:
        pms = (
            db.query(PaymentMethod)
            .filter(PaymentMethod.id.in_(pm_ids), PaymentMethod.user_id == user_id)
            .all()
        )
        pm_by_id = {pm.id: pm for pm in pms}

    all_transfers = (
        db.query(Transfer)
        .filter_by(user_id=user_id)
        .filter(Transfer.billing_month.startswith(year_prefix))
        .all()
    )
    transfers_by_month: dict[int, list[Transfer]] = {m: [] for m in range(1, 13)}
    for t in all_transfers:
        m = int(t.billing_month[5:7])
        transfers_by_month[m].append(t)

    bank_balances = compute_bank_balances_for_year(user_id, year, db)

    stamp_duty_cards = (
        db.query(PaymentMethod)
        .filter_by(user_id=user_id, type="credit_card", has_stamp_duty=True)
        .all()
    )

    results = []
    for month in range(1, 13):
        txs = txs_by_month[month]
        total_income, by_method = _transaction_summary_totals(txs, pm_by_id)

        transfers = transfers_by_month[month]
        transfers_out = sum(float(t.amount) for t in transfers if t.from_account_type == "bank")
        transfers_in = sum(float(t.amount) for t in transfers if t.to_account_type == "bank")

        month_first = f"{year:04d}-{month:02d}-01"
        stamp_duty = _compute_stamp_duty(month_first, txs, stamp_duty_cards)

        results.append({
            "year": year,
            "month": month,
            "incomes": total_income,
            "outcomes_by_method": by_method,
            "transfers_out_bank": transfers_out,
            "transfers_in_bank": transfers_in,
            "bank_balance": bank_balances[month],
            "stamp_duty": stamp_duty,
        })

    return results
