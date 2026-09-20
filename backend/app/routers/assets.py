from dataclasses import asdict
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, FiniteFloat
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models.account import Account
from app.models.asset import Asset
from app.models.user import User
from app.schemas.reporting import AsOfMonth, MAX_REPORTING_YEAR, MIN_REPORTING_YEAR
from app.services.assets import compute_assets

router = APIRouter(prefix="/assets", tags=["assets"])


class OverrideRequest(BaseModel):
    manual_override: Optional[FiniteFloat] = None
    notes: Optional[str] = None


def _asset_as_of(as_of: Annotated[str, Query()]) -> str:
    try:
        return AsOfMonth(as_of=as_of).as_of
    except ValueError as error:
        raise HTTPException(422, "Invalid asset as_of month") from error


@router.get("/{year}")
def list_assets(
    year: Annotated[int, Path(ge=MIN_REPORTING_YEAR, le=MAX_REPORTING_YEAR)],
    as_of: str = Depends(_asset_as_of),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if as_of[:4] != f"{year:04d}":
        raise HTTPException(422, "Asset as_of year must match the requested year")
    rows = compute_assets(current_user.id, year, db, as_of)
    return [asdict(r) for r in rows]


@router.put("/{year}/{asset_type}/{account_id}")
def set_override(
    year: Annotated[int, Path(ge=MIN_REPORTING_YEAR, le=MAX_REPORTING_YEAR)],
    asset_type: str,
    account_id: str,
    req: OverrideRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if asset_type not in {"saving", "investment", "pension"}:
        raise HTTPException(422, "Unknown asset type")
    account = db.query(Account).filter_by(
        id=account_id, user_id=current_user.id, type=asset_type, is_active=True
    ).first()
    # Compatibility for pre-ID frontend links: a name is accepted only when it
    # resolves to a current owned active account, never as a new asset identity.
    if account is None:
        account = db.query(Account).filter_by(
            user_id=current_user.id, type=asset_type, name=account_id, is_active=True
        ).first()
    if account is None:
        raise HTTPException(422, "Account not found or inactive")
    row = db.query(Asset).filter_by(
        user_id=current_user.id, year=year, asset_type=asset_type, account_id=account.id
    ).first()
    if row:
        row.asset_name = account.name
        row.manual_override = req.manual_override
        row.notes = req.notes
    else:
        db.add(Asset(
            user_id=current_user.id, year=year, asset_type=asset_type,
            asset_name=account.name, account_id=account.id,
            manual_override=req.manual_override, notes=req.notes,
        ))
    db.commit()
    return {"ok": True}
