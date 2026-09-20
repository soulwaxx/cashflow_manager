from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN


ZERO = Decimal("0")
ONE = Decimal("1")
MONEY_PLACES = Decimal("0.01")


class SalaryCalculationError(ValueError):
    """Raised when legacy salary or tax data is unsafe to calculate."""


@dataclass
class SalaryBreakdown:
    gross_annual: float
    social_security: float
    pension_deductible: float
    taxable_base: float
    income_tax_gross: float
    employment_deduction: float
    income_tax_net: float
    regional_surtax: float
    municipal_surtax: float
    net_annual: float
    net_monthly: float
    meal_vouchers_monthly: float
    welfare_monthly: float


def _decimal(value, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise SalaryCalculationError(f"{name} must be a finite decimal") from exc
    if not result.is_finite():
        raise SalaryCalculationError(f"{name} must be a finite decimal")
    return result


def _validate_tax_config(tax_cfg) -> None:
    b1_limit = _decimal(tax_cfg.irpef_band1_limit, "IRPEF band 1 limit")
    b2_limit = _decimal(tax_cfg.irpef_band2_limit, "IRPEF band 2 limit")
    deduction_limits = (
        _decimal(tax_cfg.employment_deduction_band1_limit, "Employment deduction band 1 limit"),
        _decimal(tax_cfg.employment_deduction_band2_limit, "Employment deduction band 2 limit"),
        _decimal(tax_cfg.employment_deduction_band3_limit, "Employment deduction band 3 limit"),
    )
    ranges = (
        _decimal(tax_cfg.employment_deduction_band2_range, "Employment deduction band 2 range"),
        _decimal(tax_cfg.employment_deduction_band3_range, "Employment deduction band 3 range"),
    )
    rates = (
        _decimal(tax_cfg.inps_rate, "INPS rate"),
        _decimal(tax_cfg.irpef_band1_rate, "IRPEF band 1 rate"),
        _decimal(tax_cfg.irpef_band2_rate, "IRPEF band 2 rate"),
        _decimal(tax_cfg.irpef_band3_rate, "IRPEF band 3 rate"),
    )
    nonnegative_amounts = (
        _decimal(tax_cfg.employment_deduction_band1_amount, "Employment deduction band 1 amount"),
        _decimal(tax_cfg.employment_deduction_band2_base, "Employment deduction band 2 base"),
        _decimal(tax_cfg.employment_deduction_band2_variable, "Employment deduction band 2 variable"),
        _decimal(tax_cfg.employment_deduction_band3_base, "Employment deduction band 3 base"),
        _decimal(tax_cfg.pension_deductibility_cap, "Pension deductibility cap"),
        _decimal(tax_cfg.employment_deduction_floor, "Employment deduction floor"),
    )
    if b1_limit <= ZERO or b1_limit >= b2_limit:
        raise SalaryCalculationError("IRPEF band limits must be positive and strictly increasing")
    if not (ZERO < deduction_limits[0] < deduction_limits[1] < deduction_limits[2]):
        raise SalaryCalculationError("Employment deduction band limits must be strictly increasing")
    if any(value <= ZERO for value in ranges):
        raise SalaryCalculationError("Employment deduction ranges must be positive")
    if any(value < ZERO or value > ONE for value in rates):
        raise SalaryCalculationError("Tax rates must be between zero and one")
    if any(value < ZERO for value in nonnegative_amounts):
        raise SalaryCalculationError("Tax amounts must not be negative")


def calculate_salary(salary_cfg, tax_cfg) -> SalaryBreakdown:
    """Calculate salary with Decimal arithmetic after guarding persisted tax data."""
    _validate_tax_config(tax_cfg)

    gross_annual = _decimal(salary_cfg.ral, "RAL")
    emp = _decimal(salary_cfg.employer_contrib_rate, "Employer contribution rate")
    vol = _decimal(salary_cfg.voluntary_contrib_rate, "Voluntary contribution rate")
    reg = _decimal(salary_cfg.regional_tax_rate, "Regional tax rate")
    mun = _decimal(salary_cfg.municipal_tax_rate, "Municipal tax rate")
    meal_vouchers_annual = _decimal(salary_cfg.meal_vouchers_annual, "Meal vouchers annual")
    welfare_annual = _decimal(salary_cfg.welfare_annual, "Welfare annual")
    try:
        salary_months = int(getattr(salary_cfg, "salary_months", 12))
    except (TypeError, ValueError) as exc:
        raise SalaryCalculationError("Salary months must be 12, 13, or 14") from exc
    if gross_annual <= ZERO:
        raise SalaryCalculationError("RAL must be positive")
    if salary_months not in {12, 13, 14}:
        raise SalaryCalculationError("Salary months must be 12, 13, or 14")
    if any(value < ZERO or value > ONE for value in (emp, vol, reg, mun)):
        raise SalaryCalculationError("Salary rates must be between zero and one")
    if meal_vouchers_annual < ZERO or welfare_annual < ZERO:
        raise SalaryCalculationError("Salary benefits must not be negative")

    # Step 1 — Social security (INPS employee contribution)
    social_security = gross_annual * _decimal(tax_cfg.inps_rate, "INPS rate")

    # Step 2 — Pension deductible (supplementary pension contributions, employer + voluntary)
    pension_deductible = min(
        (emp + vol) * gross_annual,
        _decimal(tax_cfg.pension_deductibility_cap, "Pension deductibility cap"),
    )

    # Step 3 — IRPEF taxable base
    taxable_base = gross_annual - social_security - pension_deductible
    if taxable_base < ZERO:
        raise SalaryCalculationError(
            "Salary contributions must not exceed gross annual salary after social security"
        )

    # Step 4 — IRPEF gross (progressive marginal brackets)
    b1_lim = _decimal(tax_cfg.irpef_band1_limit, "IRPEF band 1 limit")
    b2_lim = _decimal(tax_cfg.irpef_band2_limit, "IRPEF band 2 limit")
    b1_r = _decimal(tax_cfg.irpef_band1_rate, "IRPEF band 1 rate")
    b2_r = _decimal(tax_cfg.irpef_band2_rate, "IRPEF band 2 rate")
    b3_r = _decimal(tax_cfg.irpef_band3_rate, "IRPEF band 3 rate")
    if taxable_base <= b1_lim:
        income_tax_gross = taxable_base * b1_r
    elif taxable_base <= b2_lim:
        income_tax_gross = b1_lim * b1_r + (taxable_base - b1_lim) * b2_r
    else:
        income_tax_gross = b1_lim * b1_r + (b2_lim - b1_lim) * b2_r + (taxable_base - b2_lim) * b3_r

    # Step 5 — Employment deduction (detrazione per lavoro dipendente)
    d1_lim = _decimal(tax_cfg.employment_deduction_band1_limit, "Employment deduction band 1 limit")
    d2_lim = _decimal(tax_cfg.employment_deduction_band2_limit, "Employment deduction band 2 limit")
    d3_lim = _decimal(tax_cfg.employment_deduction_band3_limit, "Employment deduction band 3 limit")
    floor = _decimal(tax_cfg.employment_deduction_floor, "Employment deduction floor")
    if taxable_base <= d1_lim:
        raw_deduction = _decimal(tax_cfg.employment_deduction_band1_amount, "Employment deduction band 1 amount")
    elif taxable_base <= d2_lim:
        raw_deduction = (
            _decimal(tax_cfg.employment_deduction_band2_base, "Employment deduction band 2 base")
            + _decimal(tax_cfg.employment_deduction_band2_variable, "Employment deduction band 2 variable")
            * (d2_lim - taxable_base)
            / _decimal(tax_cfg.employment_deduction_band2_range, "Employment deduction band 2 range")
        )
    elif taxable_base <= d3_lim:
        raw_deduction = (
            _decimal(tax_cfg.employment_deduction_band3_base, "Employment deduction band 3 base")
            * (d3_lim - taxable_base)
            / _decimal(tax_cfg.employment_deduction_band3_range, "Employment deduction band 3 range")
        )
    else:
        raw_deduction = ZERO

    # Apply legal minimum floor (only when formula yields a positive value)
    employment_deduction = max(raw_deduction, floor) if raw_deduction > ZERO else ZERO

    # Step 6 — Net IRPEF
    income_tax_net = max(ZERO, income_tax_gross - employment_deduction)

    # Step 7 — Regional + municipal surtax
    regional_surtax = taxable_base * reg
    municipal_surtax = taxable_base * mun

    # Step 8 — Net annual (only voluntary pension subtracted; employer cost is not employee income)
    net_annual = gross_annual - social_security - (vol * gross_annual) - income_tax_net - regional_surtax - municipal_surtax

    if net_annual < ZERO:
        raise SalaryCalculationError("Computed net annual salary must not be negative")

    # Step 9 — Net monthly (divided by salary_months: 12, 13, or 14)
    net_monthly = (net_annual / salary_months).quantize(MONEY_PLACES, rounding=ROUND_HALF_EVEN)
    if net_monthly < ZERO:
        raise SalaryCalculationError("Computed net monthly salary must not be negative")

    # Meal vouchers and welfare are paid in 12 monthly installments regardless of salary_months
    # (tredicesima/quattordicesima does not include fringe benefits in standard Italian payroll)
    meal_vouchers_monthly = meal_vouchers_annual / 12
    welfare_monthly = welfare_annual / 12

    return SalaryBreakdown(
        gross_annual=float(gross_annual),
        social_security=float(social_security),
        pension_deductible=float(pension_deductible),
        taxable_base=float(taxable_base),
        income_tax_gross=float(income_tax_gross),
        employment_deduction=float(employment_deduction),
        income_tax_net=float(income_tax_net),
        regional_surtax=float(regional_surtax),
        municipal_surtax=float(municipal_surtax),
        net_annual=float(net_annual),
        net_monthly=float(net_monthly),
        meal_vouchers_monthly=float(meal_vouchers_monthly),
        welfare_monthly=float(welfare_monthly),
    )
