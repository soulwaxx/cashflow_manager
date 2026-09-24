import bisect
from decimal import Decimal, ROUND_HALF_EVEN

from sqlalchemy.orm import Session
from app.models.forecast import Forecast, ForecastLine, ForecastAdjustment
from app.models.transaction import Transaction

CENT = Decimal("0.01")


def auto_generate_lines(forecast: Forecast, db: Session) -> None:
    """Import monthly debit commitments still occurring in December of the base year.

    Recurrences are finite materialized transactions, not live schedules. A
    December occurrence is the explicit signal that a commitment crosses the
    base-year boundary; saved forecast lines are independent snapshots.
    """
    december = f"{forecast.base_year:04d}-12-"
    occurrences = (
        db.query(Transaction)
        .filter(
            Transaction.user_id == forecast.user_id,
            Transaction.recurrence_months.isnot(None),
            Transaction.transaction_direction == "debit",
            Transaction.date.startswith(december),
        )
        .order_by(Transaction.date.desc(), Transaction.id.desc())
        .all()
    )
    root_ids = {tx.parent_transaction_id or tx.id for tx in occurrences}
    owned_root_ids = {
        root_id for (root_id,) in db.query(Transaction.id).filter(
            Transaction.id.in_(root_ids), Transaction.user_id == forecast.user_id,
            Transaction.recurrence_months.isnot(None),
        ).all()
    } if root_ids else set()
    seen_roots: set[str] = set()
    for tx in occurrences:
        root_id = tx.parent_transaction_id or tx.id
        if root_id not in owned_root_ids or root_id in seen_roots:
            continue
        seen_roots.add(root_id)
        db.add(ForecastLine(
            forecast_id=forecast.id,
            user_id=forecast.user_id,
            source_transaction_id=root_id,
            category_id=tx.category_id,
            detail=tx.detail,
            base_amount=tx.amount,
            payment_method_id=tx.payment_method_id,
            billing_day=int(tx.date[-2:]),
        ))


def project_forecast(forecast_id: str, user_id: str, db: Session) -> dict:
    """
    Compute month-by-month projection for all lines.
    Projection period: base_year+1 through base_year+projection_years.
    effective_amount(line, month) = highest valid_from adjustment <= month, else base_amount.
    """
    forecast = db.query(Forecast).filter(
        Forecast.id == forecast_id, Forecast.user_id == user_id
    ).first()
    if not forecast:
        return {}

    start_year = forecast.base_year + 1
    end_year = forecast.base_year + forecast.projection_years
    period_from = f"{start_year:04d}-01"
    period_to = f"{end_year:04d}-12"

    lines = db.query(ForecastLine).filter_by(forecast_id=forecast_id, user_id=user_id).all()
    # Bulk-load all adjustments in one query
    line_ids = [line.id for line in lines]
    all_adjs = (
        db.query(ForecastAdjustment)
        .filter(ForecastAdjustment.forecast_line_id.in_(line_ids), ForecastAdjustment.user_id == user_id)
        .order_by(ForecastAdjustment.valid_from, ForecastAdjustment.id)
        .all()
        if line_ids else []
    )
    adj_by_line: dict[str, list] = {lid: [] for lid in line_ids}
    for a in all_adjs:
        adj_by_line[a.forecast_line_id].append(a)

    result_lines = []
    monthly_totals: dict[str, Decimal] = {
        f"{year:04d}-{month:02d}": Decimal("0")
        for year in range(start_year, end_year + 1)
        for month in range(1, 13)
    }

    for line in lines:
        adjs = adj_by_line[line.id]
        # Build sorted list of valid_from strings once per line (adjs already
        # sorted ascending by valid_from from the DB query).
        adj_dates = [a.valid_from for a in adjs]
        months_data = []
        for year in range(start_year, end_year + 1):
            for month in range(1, 13):
                month_str = f"{year:04d}-{month:02d}"
                month_first = f"{year:04d}-{month:02d}-01"
                # O(log n) lookup: find the rightmost adjustment whose
                # valid_from <= month_first.
                idx = bisect.bisect_right(adj_dates, month_first) - 1
                if idx >= 0:
                    adj = adjs[idx]
                    adj_type = getattr(adj, "adjustment_type", "fixed") or "fixed"
                    if adj_type == "percentage":
                        effective = Decimal(line.base_amount) * (1 + Decimal(adj.new_amount) / 100)
                    else:
                        effective = Decimal(adj.new_amount)
                else:
                    effective = Decimal(line.base_amount)
                effective = effective.quantize(CENT, rounding=ROUND_HALF_EVEN)
                months_data.append({"month": month_str, "effective_amount": float(effective)})
                monthly_totals[month_str] += effective

        result_lines.append({
            "line_id": line.id,
            "detail": line.detail,
            "category_id": line.category_id,
            "base_amount": float(line.base_amount),
            "billing_day": line.billing_day,
            "adjustments": [
                {
                    "id": a.id, "valid_from": a.valid_from, "new_amount": float(a.new_amount),
                    "adjustment_type": getattr(a, "adjustment_type", "fixed") or "fixed",
                }
                for a in adjs
            ],
            "months": months_data,
        })

    # Yearly totals
    yearly_totals = {}
    for month_str, total in monthly_totals.items():
        year_str = month_str[:4]
        yearly_totals[year_str] = yearly_totals.get(year_str, Decimal("0")) + total

    return {
        "forecast_id": forecast_id,
        "base_year": forecast.base_year,
        "projection_years": forecast.projection_years,
        "period": {"from": period_from, "to": period_to},
        "lines": result_lines,
        "monthly_totals": [{"month": k, "total": float(v)} for k, v in sorted(monthly_totals.items())],
        "yearly_totals": [{"year": int(k), "total": float(v)} for k, v in sorted(yearly_totals.items())],
    }
