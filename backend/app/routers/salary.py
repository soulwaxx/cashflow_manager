from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.deps import get_db, get_current_user
from app.models.account import Account
from app.models.salary import SalaryConfig
from app.models.user import User
from app.schemas.salary import (
    PensionPayrollRequest, SalaryBreakdownResponse, SalaryCalculationRequest,
    SalaryConfigCreate, SalaryResponse,
)
from app.services.pension import (
    PensionPayrollInputs, payroll_effects, preview_payroll_effects, resolve_pension_config,
)
from app.services.salary import SalaryCalculationError, calculate_salary
from app.services.tax import resolve_tax_config

router = APIRouter(prefix="/salary", tags=["salary"])


def _calculate_or_422(salary_cfg, tax_cfg, pension_effects):
    try:
        return calculate_salary(salary_cfg, tax_cfg, pension_effects)
    except (SalaryCalculationError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc


def _pension_response(result) -> dict:
    return {
        "employee_pension_contribution_annual": result.employee_pension_contribution_annual,
        "employer_pension_contribution_annual": result.employer_pension_contribution_annual,
        "tfr_contribution_annual": result.tfr_contribution_annual,
        "pension_payroll_deduction_annual": result.pension_payroll_deduction_annual,
        "pension_employer_taxable_excess_annual": result.pension_employer_taxable_excess_annual,
        "pension_cap_eligible_contributions_annual": result.pension_cap_eligible_contributions_annual,
        "pension_cap_used_annual": result.pension_cap_used_annual,
        "pension_cap_excess_annual": result.pension_cap_excess_annual,
        "pension_deductibility_cap": result.pension_deductibility_cap,
        "pension_cap_scope": result.pension_cap_scope,
    }


def _breakdown_response(result) -> dict:
    return result.__dict__.copy()


def _saved_calculation(db: Session, user_id: str, salary_cfg: SalaryConfig, as_of: str):
    tax_cfg = resolve_tax_config(db, as_of, user_id)
    if tax_cfg is None:
        raise HTTPException(422, "No tax config found for the given period")
    try:
        pension_cfg = resolve_pension_config(db, user_id, as_of)
        effects = payroll_effects(db, user_id, as_of, config=pension_cfg)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    result = _calculate_or_422(salary_cfg, tax_cfg, effects)
    return result, pension_cfg


def _salary_response(db: Session, salary_config: SalaryConfig, user_id: str) -> dict:
    result, pension_cfg = _saved_calculation(db, user_id, salary_config, salary_config.valid_from)
    return {
        "id": salary_config.id,
        "user_id": salary_config.user_id,
        "valid_from": salary_config.valid_from,
        "ral": float(salary_config.ral),
        "regional_tax_rate": float(salary_config.regional_tax_rate),
        "municipal_tax_rate": float(salary_config.municipal_tax_rate),
        "meal_vouchers_annual": float(salary_config.meal_vouchers_annual),
        "welfare_annual": float(salary_config.welfare_annual),
        "salary_months": salary_config.salary_months,
        "manual_net_override": float(salary_config.manual_net_override) if salary_config.manual_net_override is not None else None,
        "computed_net_monthly": result.computed_net_monthly,
        "effective_net_monthly": float(salary_config.manual_net_override) if salary_config.manual_net_override is not None else result.computed_net_monthly,
        "calculated_as_of": salary_config.valid_from,
        "salary_config_id": salary_config.id,
        "salary_config_valid_from": salary_config.valid_from,
        "pension_config_id": pension_cfg.id if pension_cfg else None,
        "pension_config_valid_from": pension_cfg.valid_from if pension_cfg else None,
        "pension": _pension_response(result),
        "tax_config_id": result.tax_config_id,
        "tax_config_valid_from": result.tax_config_valid_from,
    }


@router.post("/calculate", response_model=SalaryBreakdownResponse)
def preview_salary(request: SalaryCalculationRequest,
                   current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    tax_cfg = resolve_tax_config(db, request.as_of, current_user.id)
    if tax_cfg is None:
        raise HTTPException(422, "No tax config found for the given period")
    try:
        pension = None
        if request.pension is not None:
            if request.pension.account_id:
                owned = db.query(Account.id).filter(
                    Account.id == request.pension.account_id,
                    Account.user_id == current_user.id,
                    Account.type == "pension",
                    Account.is_active.is_(True),
                ).first()
                if owned is None:
                    raise HTTPException(422, "Pension account not found or inactive")
            pension = PensionPayrollInputs(
                employee_contrib_rate=request.pension.employee_contrib_rate,
                employee_contrib_annual_base=request.pension.employee_contrib_annual_base,
                employer_contrib_rate=request.pension.employer_contrib_rate,
                employer_contrib_annual_base=request.pension.employer_contrib_annual_base,
                tfr_contrib_annual=request.pension.tfr_contrib_annual,
            )
        effects = preview_payroll_effects(db, current_user.id, request.as_of, pension)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    result = _calculate_or_422(request.salary, tax_cfg, effects)
    response = _breakdown_response(result)
    response["calculated_as_of"] = request.as_of
    return response


@router.get("/breakdown", response_model=SalaryBreakdownResponse)
def salary_breakdown(as_of: Annotated[str, Query()], current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        from app.schemas.reporting import AsOfMonth
        as_of = AsOfMonth(as_of=as_of).as_of
    except ValueError as exc:
        raise HTTPException(422, "as_of must be a canonical first-of-month date") from exc
    salary_cfg = db.query(SalaryConfig).filter(
        SalaryConfig.user_id == current_user.id, SalaryConfig.valid_from <= as_of
    ).order_by(SalaryConfig.valid_from.desc(), SalaryConfig.id.asc()).first()
    if salary_cfg is None:
        raise HTTPException(404, "No salary configuration applies to this month")
    result, pension_cfg = _saved_calculation(db, current_user.id, salary_cfg, as_of)
    response = _breakdown_response(result)
    response.update({
        "calculated_as_of": as_of,
        "salary_config_id": salary_cfg.id,
        "salary_config_valid_from": salary_cfg.valid_from,
        "pension_config_id": pension_cfg.id if pension_cfg else None,
        "pension_config_valid_from": pension_cfg.valid_from if pension_cfg else None,
        "manual_net_override": float(salary_cfg.manual_net_override) if salary_cfg.manual_net_override is not None else None,
        "effective_net_monthly": float(salary_cfg.manual_net_override) if salary_cfg.manual_net_override is not None else result.computed_net_monthly,
    })
    return response


@router.get("", response_model=list[SalaryResponse])
def list_salary(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    configs = db.query(SalaryConfig).filter_by(user_id=current_user.id).order_by(SalaryConfig.valid_from).all()
    return [_salary_response(db, config, current_user.id) for config in configs]


@router.post("", response_model=SalaryResponse, status_code=201)
def create_salary(req: SalaryConfigCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    tax_cfg = resolve_tax_config(db, req.valid_from, current_user.id)
    if tax_cfg is None:
        raise HTTPException(422, "No tax config found for the given period")
    config = SalaryConfig(user_id=current_user.id, **req.model_dump())
    result, _ = _saved_calculation(db, current_user.id, config, req.valid_from)
    db.add(config)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Salary configuration already exists for this effective month")
    db.refresh(config)
    return _salary_response(db, config, current_user.id)


@router.put("/{salary_id}", response_model=SalaryResponse)
def update_salary(salary_id: str, req: SalaryConfigCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    config = db.query(SalaryConfig).filter_by(id=salary_id, user_id=current_user.id).first()
    if config is None:
        raise HTTPException(404, "Salary configuration not found")
    values = req.model_dump(exclude_unset=True)
    candidate_values = {
        "valid_from": config.valid_from, "ral": config.ral,
        "regional_tax_rate": config.regional_tax_rate,
        "municipal_tax_rate": config.municipal_tax_rate,
        "meal_vouchers_annual": config.meal_vouchers_annual,
        "welfare_annual": config.welfare_annual, "salary_months": config.salary_months,
        "manual_net_override": config.manual_net_override,
    }
    candidate_values.update(values)
    candidate = SimpleNamespace(**candidate_values)
    _saved_calculation(db, current_user.id, candidate, req.valid_from)
    for field, value in values.items():
        setattr(config, field, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Salary configuration already exists for this effective month")
    db.refresh(config)
    return _salary_response(db, config, current_user.id)


@router.delete("/{salary_id}", status_code=204)
def delete_salary(salary_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    config = db.query(SalaryConfig).filter_by(id=salary_id, user_id=current_user.id).first()
    if config is None:
        raise HTTPException(404, "Salary configuration not found")
    earliest = db.query(SalaryConfig).filter_by(user_id=current_user.id).order_by(SalaryConfig.valid_from).first()
    if earliest and earliest.id == salary_id:
        raise HTTPException(400, "Cannot delete the earliest salary config row")
    db.delete(config)
    db.commit()
    return Response(status_code=204)
