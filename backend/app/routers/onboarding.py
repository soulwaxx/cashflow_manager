from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.deps import get_db, get_current_user
from app.models.user import User, UserSetting
from app.models.payment_method import CardBankLinkHistory, MainBankHistory, PaymentMethod
from app.models.category import Category
from app.models.account import Account
from app.models.salary import SalaryConfig
from app.schemas.onboarding import OnboardingPayload
from app.services.seed import DEFAULT_CATEGORIES
from app.services.salary import SalaryCalculationError, calculate_salary
from app.services.tax import resolve_tax_config

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

def _set_setting(db, user_id, key, value):
    row = db.query(UserSetting).filter_by(user_id=user_id, key=key).first()
    if row:
        row.value = str(value)
    else:
        db.add(UserSetting(user_id=user_id, key=key, value=str(value)))

def _get_setting(db, user_id, key):
    row = db.query(UserSetting).filter_by(user_id=user_id, key=key).first()
    return row.value if row else None

@router.get("/status")
def onboarding_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    complete = _get_setting(db, current_user.id, "onboarding_complete") == "true"
    return {"complete": complete}

@router.post("")
def submit_onboarding(
    payload: OnboardingPayload,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if _get_setting(db, current_user.id, "onboarding_complete") == "true":
        raise HTTPException(status_code=409, detail="Onboarding has already been completed")

    breakdown = None
    if payload.salary:
        tax_cfg = resolve_tax_config(db, payload.tracking_start_date[:7], current_user.id)
        if not tax_cfg:
            raise HTTPException(422, "No tax config found for the given period")
        try:
            breakdown = calculate_salary(payload.salary, tax_cfg)
        except SalaryCalculationError as exc:
            raise HTTPException(422, str(exc)) from exc

    _set_setting(db, current_user.id, "tracking_start_date", payload.tracking_start_date)

    # Main bank
    main_pm = PaymentMethod(
        user_id=current_user.id, name=payload.main_bank.name,
        type="bank", is_main_bank=True,
    )
    db.add(main_pm)
    db.flush()
    _set_setting(db, current_user.id, f"opening_bank_balance_{main_pm.id}", payload.main_bank.opening_balance)
    db.add(MainBankHistory(
        user_id=current_user.id, payment_method_id=main_pm.id,
        valid_from=payload.tracking_start_date, opening_balance=payload.main_bank.opening_balance,
    ))

    # Additional banks
    bank_name_to_id = {payload.main_bank.name: main_pm.id}
    for ab in (payload.additional_banks or []):
        pm = PaymentMethod(user_id=current_user.id, name=ab.name, type="bank")
        db.add(pm)
        db.flush()
        bank_name_to_id[ab.name] = pm.id
        _set_setting(db, current_user.id, f"opening_bank_balance_{pm.id}", ab.opening_balance)

    # Other payment methods
    for pmi in (payload.payment_methods or []):
        linked_id = bank_name_to_id.get(pmi.linked_bank_name) if pmi.linked_bank_name else None
        pm = PaymentMethod(
            user_id=current_user.id, name=pmi.name, type=pmi.type,
            linked_bank_id=linked_id, opening_balance=pmi.opening_balance,
        )
        db.add(pm)
        db.flush()
        if pmi.type in {"debit_card", "credit_card", "revolving"}:
            db.add(CardBankLinkHistory(
                user_id=current_user.id,
                card_payment_method_id=pm.id,
                linked_bank_id=linked_id,
                valid_from=payload.tracking_start_date,
            ))
        if pmi.type == "prepaid" and pmi.opening_balance is not None:
            _set_setting(db, current_user.id, f"opening_bank_balance_{pm.id}", pmi.opening_balance)

    # Saving / investment accounts have stable owned identities.
    for sa in (payload.saving_accounts or []):
        db.add(Account(
            user_id=current_user.id, type="saving", name=sa.name,
            opening_balance=sa.opening_balance,
        ))
    for ia in (payload.investment_accounts or []):
        db.add(Account(
            user_id=current_user.id, type="investment", name=ia.name,
            opening_balance=ia.opening_balance,
        ))

    # Default categories (Saving/* start inactive — tracked via Transfers)
    for type_, sub_type in DEFAULT_CATEGORIES:
        db.add(Category(
            user_id=current_user.id, type=type_, sub_type=sub_type,
            is_active=(type_ != "Saving"),
        ))

    # Salary (optional)
    if payload.salary:
        if payload.salary.employer_contrib_rate > 0 or payload.salary.voluntary_contrib_rate > 0:
            db.add(Account(
                user_id=current_user.id, type="pension", name="Pension", opening_balance=0,
            ))
        db.add(SalaryConfig(
            user_id=current_user.id,
            valid_from=payload.tracking_start_date,
            ral=payload.salary.ral,
            employer_contrib_rate=payload.salary.employer_contrib_rate,
            voluntary_contrib_rate=payload.salary.voluntary_contrib_rate,
            regional_tax_rate=payload.salary.regional_tax_rate,
            municipal_tax_rate=payload.salary.municipal_tax_rate,
            meal_vouchers_annual=payload.salary.meal_vouchers_annual,
            welfare_annual=payload.salary.welfare_annual,
            salary_months=payload.salary.salary_months,
            manual_net_override=payload.salary.manual_net_override,
            computed_net_monthly=breakdown.net_monthly,
        ))

    _set_setting(db, current_user.id, "onboarding_complete", "true")
    db.commit()
    return {"ok": True}
