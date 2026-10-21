from __future__ import annotations

from datetime import date
from decimal import Decimal
from fractions import Fraction

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models.account import Account
from app.models.pension import PensionBalanceSnapshot, PensionConfig
from app.models.transfer import Transfer
from app.models.user import User
from app.schemas.pension import (
    PensionAccountResponse, PensionAnnualizedSummary, PensionBalanceSnapshotCreate,
    PensionBalanceSnapshotResponse, PensionConfigCreate, PensionConfigResponse,
    PensionSummaryResponse,
)
from app.schemas.reporting import MAX_REPORTING_YEAR, MIN_REPORTING_YEAR
from app.services.pension import (
    _monthly_credit_fractions, _round_fraction_money, payroll_effects,
    resolve_config_from_loaded, resolve_pension_config,
)

router = APIRouter(prefix="/pension", tags=["pension"])


class OpeningBalanceUpdate(BaseModel):
    amount: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    month: str

    @field_validator("month")
    @classmethod
    def canonical_month(cls, value: str) -> str:
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            raise ValueError("Month must be a canonical YYYY-MM-01 date") from None
        if parsed.isoformat() != value or parsed.day != 1:
            raise ValueError("Month must be a canonical YYYY-MM-01 date")
        return value


def _owned_active_pension(db: Session, user_id: str, account_id: str) -> Account:
    account = db.query(Account).filter_by(
        id=account_id, user_id=user_id, type="pension", is_active=True
    ).first()
    if account is None:
        raise HTTPException(422, "Pension account not found or inactive")
    return account


def _config_response(row: PensionConfig) -> PensionConfigResponse:
    return PensionConfigResponse.model_validate(row)


def _snapshot_response(row: PensionBalanceSnapshot) -> PensionBalanceSnapshotResponse:
    return PensionBalanceSnapshotResponse.model_validate(row)


def _rollback_integrity(db: Session, message: str):
    db.rollback()
    raise HTTPException(409, message)


@router.get("/configs", response_model=list[PensionConfigResponse])
def list_configs(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(PensionConfig).filter_by(user_id=current_user.id).order_by(PensionConfig.valid_from, PensionConfig.id).all()
    return [_config_response(row) for row in rows]


@router.post("/configs", response_model=PensionConfigResponse, status_code=201)
def create_config(req: PensionConfigCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _owned_active_pension(db, current_user.id, req.account_id)
    row = PensionConfig(user_id=current_user.id, **req.model_dump())
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        _rollback_integrity(db, "A pension configuration already exists for this effective month or destination is invalid")
    db.refresh(row)
    return _config_response(row)


@router.put("/configs/{config_id}", response_model=PensionConfigResponse)
def update_config(config_id: str, req: PensionConfigCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.query(PensionConfig).filter_by(id=config_id, user_id=current_user.id).first()
    if row is None:
        raise HTTPException(404, "Pension configuration not found")
    _owned_active_pension(db, current_user.id, req.account_id)
    for field, value in req.model_dump().items():
        setattr(row, field, value)
    try:
        db.commit()
    except IntegrityError:
        _rollback_integrity(db, "A pension configuration already exists for this effective month or destination is invalid")
    db.refresh(row)
    return _config_response(row)


@router.delete("/configs/{config_id}", status_code=204)
def delete_config(config_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.query(PensionConfig).filter_by(id=config_id, user_id=current_user.id).first()
    if row is None:
        raise HTTPException(404, "Pension configuration not found")
    db.delete(row)
    db.commit()
    return Response(status_code=204)


@router.patch("/accounts/{account_id}/opening-balance", response_model=PensionAccountResponse)
def update_opening_balance(account_id: str, req: OpeningBalanceUpdate,
                           current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    account = _owned_active_pension(db, current_user.id, account_id)
    conflicting_snapshot = db.query(PensionBalanceSnapshot.id).filter(
        PensionBalanceSnapshot.user_id == current_user.id,
        PensionBalanceSnapshot.account_id == account_id,
        PensionBalanceSnapshot.as_of_month < req.month,
    ).first()
    if conflicting_snapshot:
        raise HTTPException(409, "Opening balance month cannot be after an existing pension snapshot")
    account.opening_balance = req.amount
    account.opening_balance_month = req.month
    db.commit()
    db.refresh(account)
    return account


@router.get("/accounts/{account_id}/snapshots", response_model=list[PensionBalanceSnapshotResponse])
def list_snapshots(account_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _owned_active_pension(db, current_user.id, account_id)
    rows = db.query(PensionBalanceSnapshot).filter_by(
        user_id=current_user.id, account_id=account_id
    ).order_by(PensionBalanceSnapshot.as_of_month).all()
    return [_snapshot_response(row) for row in rows]


@router.put("/accounts/{account_id}/snapshots/{as_of_month}", response_model=PensionBalanceSnapshotResponse)
def upsert_snapshot(account_id: str, as_of_month: str, req: PensionBalanceSnapshotCreate,
                    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if req.account_id != account_id or req.as_of_month != as_of_month:
        raise HTTPException(422, "Snapshot body account_id/as_of_month must match the URL")
    account = _owned_active_pension(db, current_user.id, account_id)
    if as_of_month < (account.opening_balance_month or "9999-99-99"):
        raise HTTPException(422, "Snapshot cannot precede the pension opening month")
    row = db.query(PensionBalanceSnapshot).filter_by(
        user_id=current_user.id, account_id=account_id, as_of_month=as_of_month
    ).first()
    if row is None:
        row = PensionBalanceSnapshot(
            user_id=current_user.id, account_id=account_id,
            as_of_month=as_of_month, balance=req.balance, source=req.source, notes=req.notes,
        )
        db.add(row)
    else:
        row.balance, row.source, row.notes = req.balance, req.source, req.notes
    try:
        db.commit()
    except IntegrityError:
        _rollback_integrity(db, "Snapshot already exists or references an invalid account")
    db.refresh(row)
    return _snapshot_response(row)


@router.delete("/accounts/{account_id}/snapshots/{as_of_month}", status_code=204)
def delete_snapshot(account_id: str, as_of_month: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _owned_active_pension(db, current_user.id, account_id)
    row = db.query(PensionBalanceSnapshot).filter_by(
        user_id=current_user.id, account_id=account_id, as_of_month=as_of_month
    ).first()
    if row is None:
        raise HTTPException(404, "Pension snapshot not found")
    db.delete(row)
    db.commit()
    return Response(status_code=204)


@router.get("/summary", response_model=PensionSummaryResponse)
def pension_summary(year: int = Query(ge=MIN_REPORTING_YEAR, le=MAX_REPORTING_YEAR),
                    as_of: str = Query(...), current_user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    try:
        parsed = date.fromisoformat(as_of)
        if parsed.isoformat() != as_of or parsed.day != 1:
            raise ValueError
    except ValueError:
        raise HTTPException(422, "as_of must be a canonical YYYY-MM-01 date") from None
    if parsed.year != year:
        raise HTTPException(422, "as_of year must match year")
    try:
        config = resolve_pension_config(db, current_user.id, as_of)
        effects = payroll_effects(db, current_user.id, as_of, config=config)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    configs = db.query(PensionConfig).filter(
        PensionConfig.user_id == current_user.id,
        PensionConfig.valid_from <= as_of,
    ).order_by(PensionConfig.valid_from, PensionConfig.id).all()
    components = {"employee": Fraction(0), "employer": Fraction(0), "tfr": Fraction(0)}
    for month in range(1, parsed.month + 1):
        cutoff = date(year, month, 1)
        active = resolve_config_from_loaded(configs, cutoff)
        employee, employer, tfr = _monthly_credit_fractions(active, cutoff)
        components["employee"] += employee
        components["employer"] += employer
        components["tfr"] += tfr
    def money(value: Decimal | Fraction) -> float:
        exact = value if isinstance(value, Fraction) else Fraction(value)
        return float(_round_fraction_money(exact))

    return {
        "year": year, "as_of": as_of,
        "config": _config_response(config).model_dump(mode="json") if config else None,
        "year_to_date": {key: money(value) for key, value in components.items()},
        "annualized": {
            "employee": money(effects.components.employee_annual),
            "employer": money(effects.components.employer_annual),
            "tfr": money(effects.components.tfr_annual),
            "eligible_contributions": money(effects.components.employee_annual + effects.components.employer_annual),
            "cap_used": money(effects.cap_used), "cap_excess": money(effects.cap_excess),
            "cap": money(effects.deductibility_cap), "cap_scope": effects.cap_scope,
            "tax_config_valid_from": effects.tax_config_valid_from,
        },
    }
