from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.deps import get_db, get_current_user
from app.models.user import User
from app.models.salary import SalaryConfig
from app.schemas.salary import SalaryCalculationRequest, SalaryConfigCreate
from app.services.salary import SalaryCalculationError, calculate_salary
from app.services.tax import resolve_tax_config

router = APIRouter(prefix="/salary", tags=["salary"])


def _calculate_or_422(salary_cfg, tax_cfg):
    try:
        return calculate_salary(salary_cfg, tax_cfg)
    except SalaryCalculationError as exc:
        raise HTTPException(422, str(exc)) from exc


def _salary_response(salary_config: SalaryConfig) -> dict:
    response = {
        column.name: getattr(salary_config, column.name)
        for column in salary_config.__table__.columns
    }
    response["effective_net_monthly"] = (
        salary_config.manual_net_override
        if salary_config.manual_net_override is not None
        else salary_config.computed_net_monthly
    )
    return response


# /calculate MUST be registered before /{salary_id} to avoid route shadowing
@router.get("/calculate")
def preview_salary(
    request: Annotated[SalaryCalculationRequest, Query()],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tax_cfg = resolve_tax_config(db, request.as_of, current_user.id)
    if not tax_cfg:
        raise HTTPException(422, "No tax config found for the given period")

    cfg = SalaryConfigCreate(
        valid_from=request.as_of, **request.model_dump(exclude={"as_of"})
    )
    return _calculate_or_422(cfg, tax_cfg).__dict__


@router.get("")
def list_salary(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [
        _salary_response(config)
        for config in db.query(SalaryConfig).filter_by(user_id=current_user.id).order_by(SalaryConfig.valid_from)
    ]


@router.post("")
def create_salary(req: SalaryConfigCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    tax_cfg = resolve_tax_config(db, req.valid_from[:7], current_user.id)
    if not tax_cfg:
        raise HTTPException(422, "No tax config found for the given period")
    breakdown = _calculate_or_422(req, tax_cfg)
    sc = SalaryConfig(
        user_id=current_user.id,
        **req.model_dump(),
        computed_net_monthly=breakdown.net_monthly,
    )
    db.add(sc)
    db.commit()
    db.refresh(sc)
    return _salary_response(sc)


@router.put("/{salary_id}")
def update_salary(salary_id: str, req: SalaryConfigCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    sc = db.query(SalaryConfig).filter_by(id=salary_id, user_id=current_user.id).first()
    if not sc:
        raise HTTPException(404, "Not found")
    tax_cfg = resolve_tax_config(db, req.valid_from[:7], current_user.id)
    if not tax_cfg:
        raise HTTPException(422, "No tax config found for the given period")
    breakdown = _calculate_or_422(req, tax_cfg)

    values = req.model_dump(exclude_none=True)
    if "manual_net_override" in req.model_fields_set:
        values["manual_net_override"] = req.manual_net_override
    for field, val in values.items():
        setattr(sc, field, val)
    sc.computed_net_monthly = breakdown.net_monthly
    db.commit()
    db.refresh(sc)
    return _salary_response(sc)


@router.delete("/{salary_id}")
def delete_salary(salary_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    sc = db.query(SalaryConfig).filter_by(id=salary_id, user_id=current_user.id).first()
    if not sc:
        raise HTTPException(404, "Not found")
    earliest = db.query(SalaryConfig).filter_by(user_id=current_user.id).order_by(SalaryConfig.valid_from).first()
    if earliest and earliest.id == salary_id:
        raise HTTPException(400, "Cannot delete the earliest salary config row")
    db.delete(sc)
    db.commit()
    return {"ok": True}
