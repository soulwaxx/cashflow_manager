from typing import List, Optional
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models.transaction import Transaction
from app.models.account import Account
from app.models.category import Category
from app.models.transfer import Transfer


def category_spending(
    user_id: str,
    from_ym: str,
    to_ym: str,
    db: Session,
    category_ids: Optional[List[str]] = None,
    payment_method_ids: Optional[List[str]] = None,
    direction: str = "all",
) -> list:
    # billing_month is stored as "YYYY-MM-DD" (first day of month);
    # from_ym/to_ym arrive as "YYYY-MM"
    from_date = from_ym[:7] + "-01"
    to_date = to_ym[:7] + "-01"

    if from_date > to_date:
        return []

    q = (
        db.query(
            Transaction.category_id,
            Transaction.billing_month,
            func.sum(Transaction.amount).label("total_amount"),
        )
        .filter(
            Transaction.user_id == user_id,
            Transaction.billing_month >= from_date,
            Transaction.billing_month <= to_date,
        )
    )
    if direction != "all":
        q = q.filter(Transaction.transaction_direction == direction)
    if category_ids:
        q = q.filter(Transaction.category_id.in_(category_ids))
    if payment_method_ids:
        q = q.filter(Transaction.payment_method_id.in_(payment_method_ids))

    rows = q.group_by(Transaction.category_id, Transaction.billing_month).all()

    if not rows:
        return []

    cat_ids = {r.category_id for r in rows if r.category_id}
    cats = {
        c.id: c
        for c in db.query(Category)
        .filter(Category.user_id == user_id, Category.id.in_(cat_ids))
        .all()
    }

    result = []
    for row in rows:
        cat = cats.get(row.category_id)
        result.append({
            "category_id": row.category_id,
            "type": cat.type if cat else None,
            "sub_type": cat.sub_type if cat else None,
            "month": row.billing_month[:7],
            "total_amount": round(float(row.total_amount), 2),
        })
    return result


def transfer_spending(user_id: str, from_ym: str, to_ym: str, db: Session) -> list:
    """Aggregate transfers to saving/investment/pension accounts by month."""
    from_date = from_ym[:7] + "-01"
    to_date = to_ym[:7] + "-01"

    if from_date > to_date:
        return []

    stable_rows = (
        db.query(
            Transfer.to_account_id,
            Transfer.billing_month,
            func.sum(Transfer.amount).label("total_amount"),
        )
        .filter(
            Transfer.user_id == user_id,
            Transfer.billing_month >= from_date,
            Transfer.billing_month <= to_date,
            Transfer.to_account_id.is_not(None),
        )
        .group_by(Transfer.to_account_id, Transfer.billing_month)
        .all()
    )
    account_ids = {row.to_account_id for row in stable_rows}
    accounts = {
        account.id: account
        for account in db.query(Account).filter(
            Account.user_id == user_id,
            Account.id.in_(account_ids),
            Account.type.in_(["saving", "investment", "pension"]),
        ).all()
    } if account_ids else {}

    result = []
    for row in stable_rows:
        account = accounts.get(row.to_account_id)
        # Do not expose or aggregate a corrupt reference to another user's
        # account. Stable rows always use the current owned account label.
        if account is not None:
            result.append({
                "to_account_type": account.type,
                "to_account_name": account.name,
                "month": row.billing_month[:7],
                "total_amount": round(float(row.total_amount), 2),
            })

    # Name snapshots remain only for historical rows without a stable account
    # ID. They must never be mixed into a stable account's identity grouping.
    legacy_rows = (
        db.query(
            Transfer.to_account_type,
            Transfer.to_account_name,
            Transfer.billing_month,
            func.sum(Transfer.amount).label("total_amount"),
        )
        .filter(
            Transfer.user_id == user_id,
            Transfer.billing_month >= from_date,
            Transfer.billing_month <= to_date,
            Transfer.to_account_id.is_(None),
            Transfer.to_account_type.in_(["saving", "investment", "pension"]),
        )
        .group_by(Transfer.to_account_type, Transfer.to_account_name, Transfer.billing_month)
        .all()
    )
    result.extend({
        "to_account_type": row.to_account_type,
        "to_account_name": row.to_account_name,
        "month": row.billing_month[:7],
        "total_amount": round(float(row.total_amount), 2),
    } for row in legacy_rows)
    return result
