from dataclasses import dataclass
from typing import Literal, Optional

from dateutil.parser import parse as parse_date
from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models.account import Account
from app.models.payment_method import PaymentMethod
from app.models.transfer import Transfer
from app.models.user import User
from app.schemas.transfer import TransferCreate, TransferUpdate

router = APIRouter(prefix="/transfers", tags=["transfers"])


@dataclass(frozen=True)
class _ResolvedAccount:
    name: str
    account_id: Optional[str]
    payment_method_id: Optional[str]

    @property
    def identity(self) -> tuple[str, str]:
        if self.payment_method_id is not None:
            return ("bank", self.payment_method_id)
        assert self.account_id is not None
        return ("account", self.account_id)


def _validate_account(
    db: Session,
    user_id: str,
    account_type: str,
    account_id: Optional[str],
    account_name: Optional[str],
) -> _ResolvedAccount:
    """Resolve an owned active endpoint without creating name-derived accounts.

    Account names remain a compatibility-only input for clients predating stable
    IDs. They must resolve to exactly the current owned active account; they can
    never introduce an account or revive an inactive one.
    """
    if account_type == "bank":
        query = db.query(PaymentMethod).filter_by(
            user_id=user_id, type="bank", is_active=True
        )
        pm = query.filter_by(id=account_id).first() if account_id else query.filter_by(name=account_name).first()
        if pm is None:
            raise HTTPException(422, "Bank account not found or inactive")
        if account_id and account_name and pm.name != account_name:
            raise HTTPException(422, "Bank account ID and name do not match")
        return _ResolvedAccount(pm.name, None, pm.id)

    query = db.query(Account).filter_by(
        user_id=user_id, type=account_type, is_active=True
    )
    account = query.filter_by(id=account_id).first() if account_id else query.filter_by(name=account_name).first()
    if account is None:
        raise HTTPException(422, f"{account_type.title()} account not found or inactive")
    if account_id and account_name and account.name != account_name:
        raise HTTPException(422, "Account ID and name do not match")
    return _ResolvedAccount(account.name, account.id, None)


def _promote_transfer_series_root_if_needed(db: Session, user_id: str, transfer: Transfer) -> None:
    """When deleting a recurring root as single, promote the next row to root.

    Without this, deleting the root can violate the self-FK because children still
    reference the deleted id.
    """
    if transfer.parent_transfer_id is not None:
        return

    children = (
        db.query(Transfer)
        .filter_by(user_id=user_id, parent_transfer_id=transfer.id)
        .order_by(Transfer.date.asc(), Transfer.created_at.asc(), Transfer.id.asc())
        .all()
    )
    if not children:
        return

    new_root = children[0]
    new_root.parent_transfer_id = None
    for child in children[1:]:
        child.parent_transfer_id = new_root.id


@router.get("")
def list_transfers(
    billing_month: Optional[str] = None,
    from_account: Optional[str] = None,
    to_account: Optional[str] = None,
    limit: Optional[int] = Query(None, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if billing_month is None and from_account is None and to_account is None and limit is None:
        raise HTTPException(400, "At least one of billing_month, from_account, to_account, or limit is required")
    q = db.query(Transfer).filter_by(user_id=current_user.id)
    if billing_month:
        q = q.filter(Transfer.billing_month.startswith(billing_month))
    if from_account:
        q = q.filter_by(from_account_name=from_account)
    if to_account:
        q = q.filter_by(to_account_name=to_account)
    # Keep pagination stable when many rows share the same date.
    q = q.order_by(Transfer.date.desc(), Transfer.created_at.desc(), Transfer.id.desc()).offset(offset)
    if limit is not None:
        q = q.limit(limit)
    return q.all()


@router.post("")
def create_transfer(
    req: TransferCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tx_date = parse_date(req.date).date()
    bm = tx_date.replace(day=1)  # transfers always bill current month
    from_account = _validate_account(
        db, current_user.id, req.from_account_type, req.from_account_id, req.from_account_name
    )
    to_account = _validate_account(
        db, current_user.id, req.to_account_type, req.to_account_id, req.to_account_name
    )
    if from_account.identity == to_account.identity:
        raise HTTPException(422, "Transfer endpoints must be different accounts")

    transfer_fields = {
        "user_id": current_user.id,
        "detail": req.detail,
        "amount": req.amount,
        "from_account_type": req.from_account_type,
        "from_account_name": from_account.name,
        "from_account_id": from_account.account_id,
        "from_payment_method_id": from_account.payment_method_id,
        "to_account_type": req.to_account_type,
        "to_account_name": to_account.name,
        "to_account_id": to_account.account_id,
        "to_payment_method_id": to_account.payment_method_id,
        "recurrence_months": req.recurrence_months,
        "notes": req.notes,
    }
    if req.recurrence_months:
        first = None
        for i in range(req.recurrence_months):
            occ_date = tx_date + relativedelta(months=i)
            t = Transfer(
                **transfer_fields,
                date=str(occ_date),
                billing_month=str(occ_date.replace(day=1)),
            )
            db.add(t)
            db.flush()
            if i == 0:
                first = t
            else:
                t.parent_transfer_id = first.id
        db.commit()
        db.refresh(first)
        return first

    t = Transfer(
        **transfer_fields,
        date=req.date,
        billing_month=str(bm),
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


@router.get("/{transfer_id}")
def get_transfer(transfer_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    t = db.query(Transfer).filter_by(id=transfer_id, user_id=current_user.id).first()
    if not t:
        raise HTTPException(404, "Not found")
    return t


@router.put("/{transfer_id}")
def update_transfer(
    transfer_id: str, req: TransferUpdate,
    cascade: Literal["single", "future", "all"] = Query("single"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    t = db.query(Transfer).filter_by(id=transfer_id, user_id=current_user.id).first()
    if not t:
        raise HTTPException(404, "Not found")
    payload = req.model_dump(exclude_unset=True)
    for field in ("date", "detail", "amount"):
        if field in payload and payload[field] is None:
            raise HTTPException(422, f"{field} cannot be null")
    root_id = t.parent_transfer_id or t.id
    if cascade == "all":
        rows = db.query(Transfer).filter(
            (Transfer.id == root_id) | (Transfer.parent_transfer_id == root_id)
        ).filter_by(user_id=current_user.id).all()
    elif cascade == "future":
        rows = db.query(Transfer).filter(
            ((Transfer.id == root_id) | (Transfer.parent_transfer_id == root_id)),
            Transfer.date >= t.date,
        ).filter_by(user_id=current_user.id).all()
    else:
        rows = [t]
    # Split fields: date must only apply to the target row, not siblings
    cascade_fields = {k: v for k, v in payload.items() if k != "date"}
    target_fields = payload

    for row in rows:
        fields = target_fields if row.id == transfer_id else cascade_fields
        for field, val in fields.items():
            setattr(row, field, val)
        # Recompute billing_month — transfers always bill the current month (no credit-card shift)
        row.billing_month = str(parse_date(row.date).date().replace(day=1))
    db.commit()
    db.refresh(t)
    return t


@router.delete("/{transfer_id}")
def delete_transfer(
    transfer_id: str,
    cascade: Literal["single", "future", "all"] = Query("single"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    t = db.query(Transfer).filter_by(id=transfer_id, user_id=current_user.id).first()
    if not t:
        raise HTTPException(404, "Not found")
    root_id = t.parent_transfer_id or t.id
    if cascade == "all":
        to_del = db.query(Transfer).filter(
            (Transfer.id == root_id) | (Transfer.parent_transfer_id == root_id)
        ).filter_by(user_id=current_user.id).all()
    elif cascade == "future":
        to_del = db.query(Transfer).filter(
            ((Transfer.id == root_id) | (Transfer.parent_transfer_id == root_id)),
            Transfer.date >= t.date,
        ).filter_by(user_id=current_user.id).all()
    else:
        _promote_transfer_series_root_if_needed(db, current_user.id, t)
        to_del = [t]
    delete_ids = [row.id for row in to_del]
    if delete_ids:
        db.query(Transfer).filter(
            Transfer.user_id == current_user.id,
            Transfer.parent_transfer_id.in_(delete_ids),
        ).update({Transfer.parent_transfer_id: None}, synchronize_session=False)
        db.flush()

    for row in sorted(to_del, key=lambda item: item.id == root_id):
        db.delete(row)
    db.commit()
    return {"ok": True}
