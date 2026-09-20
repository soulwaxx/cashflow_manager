from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models.account import Account
from app.models.user import User
from app.schemas.account import AccountCreate

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("")
def list_accounts(
    account_type: str | None = Query(None, alias="type"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Account).filter_by(user_id=current_user.id, is_active=True)
    if account_type is not None:
        if account_type not in {"saving", "investment", "pension"}:
            raise HTTPException(422, "Unknown account type")
        query = query.filter_by(type=account_type)
    return query.order_by(Account.type, Account.name).all()


@router.post("")
def create_account(
    req: AccountCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # SQLite's default unique comparison is case-sensitive; keep account selection
    # unambiguous for the case-insensitive onboarding validation and legacy fallback.
    if db.query(Account).filter(
        Account.user_id == current_user.id,
        Account.type == req.type,
        func.lower(Account.name) == req.name.casefold(),
    ).first():
        raise HTTPException(422, "An account with this name already exists")
    account = Account(user_id=current_user.id, **req.model_dump())
    db.add(account)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(422, "An account with this name already exists")
    db.refresh(account)
    return account
