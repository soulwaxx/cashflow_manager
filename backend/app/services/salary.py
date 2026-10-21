from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN

from app.services.pension import PensionComponents, PensionPayrollEffects

ZERO = Decimal("0")
ONE = Decimal("1")
MONEY_PLACES = Decimal("0.01")


class SalaryCalculationError(ValueError):
    """Raised when salary or tax data is unsafe to calculate."""


@dataclass
class SalaryBreakdown:
    gross_annual: float
    social_security: float
    employee_pension_contribution_annual: float
    employer_pension_contribution_annual: float
    tfr_contribution_annual: float
    pension_payroll_deduction_annual: float
    pension_employer_taxable_excess_annual: float
    pension_cap_eligible_contributions_annual: float
    pension_cap_used_annual: float
    pension_cap_excess_annual: float
    pension_deductibility_cap: float
    pension_cap_scope: str
    tax_config_id: str
    tax_config_valid_from: str
    taxable_base: float
    income_tax_gross: float
    employment_deduction: float
    income_tax_net: float
    regional_surtax: float
    municipal_surtax: float
    net_annual: float
    computed_net_monthly: float
    meal_vouchers_monthly: float
    welfare_monthly: float
    salary_months: int


def _decimal(value, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise SalaryCalculationError(f"{name} must be a finite decimal") from exc
    if not result.is_finite():
        raise SalaryCalculationError(f"{name} must be a finite decimal")
    return result


def _round(value: Decimal) -> Decimal:
    return value.quantize(MONEY_PLACES, rounding=ROUND_HALF_EVEN)


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
    nonnegative = (
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
    if any(value < ZERO for value in nonnegative):
        raise SalaryCalculationError("Tax amounts must not be negative")


def calculate_salary(salary_cfg, tax_cfg, pension_effects=None) -> SalaryBreakdown:
    """Calculate gross-to-net with raw M2 pension values and final-only cent rounding."""
    _validate_tax_config(tax_cfg)
    if pension_effects is None:
        pension_effects = PensionPayrollEffects(
            components=PensionComponents(ZERO, ZERO, ZERO),
            deductibility_cap=_decimal(tax_cfg.pension_deductibility_cap, "Pension deductibility cap"),
            cap_used=ZERO, cap_excess=ZERO, payroll_deduction=ZERO,
            employer_taxable_excess=ZERO, tax_config_id="", tax_config_valid_from="",
        )
    gross = _decimal(salary_cfg.ral, "RAL")
    regional = _decimal(salary_cfg.regional_tax_rate, "Regional tax rate")
    municipal = _decimal(salary_cfg.municipal_tax_rate, "Municipal tax rate")
    meal_vouchers = _decimal(salary_cfg.meal_vouchers_annual, "Meal vouchers annual")
    welfare = _decimal(salary_cfg.welfare_annual, "Welfare annual")
    try:
        salary_months = int(getattr(salary_cfg, "salary_months", 12))
    except (TypeError, ValueError) as exc:
        raise SalaryCalculationError("Salary months must be 12, 13, or 14") from exc
    if gross <= ZERO:
        raise SalaryCalculationError("RAL must be positive")
    if salary_months not in {12, 13, 14}:
        raise SalaryCalculationError("Salary months must be 12, 13, or 14")
    if any(value < ZERO or value > ONE for value in (regional, municipal)):
        raise SalaryCalculationError("Salary rates must be between zero and one")
    if meal_vouchers < ZERO or welfare < ZERO:
        raise SalaryCalculationError("Salary benefits must not be negative")

    components = pension_effects.components
    employee = components.employee_annual
    employer = components.employer_annual
    tfr = components.tfr_annual
    social_security = gross * _decimal(tax_cfg.inps_rate, "INPS rate")
    taxable_base = gross + employer - social_security - pension_effects.cap_used
    if taxable_base < ZERO:
        raise SalaryCalculationError("Salary contributions must not exceed gross annual salary after social security")

    b1_lim = _decimal(tax_cfg.irpef_band1_limit, "IRPEF band 1 limit")
    b2_lim = _decimal(tax_cfg.irpef_band2_limit, "IRPEF band 2 limit")
    b1_rate = _decimal(tax_cfg.irpef_band1_rate, "IRPEF band 1 rate")
    b2_rate = _decimal(tax_cfg.irpef_band2_rate, "IRPEF band 2 rate")
    b3_rate = _decimal(tax_cfg.irpef_band3_rate, "IRPEF band 3 rate")
    if taxable_base <= b1_lim:
        income_tax_gross = taxable_base * b1_rate
    elif taxable_base <= b2_lim:
        income_tax_gross = b1_lim * b1_rate + (taxable_base - b1_lim) * b2_rate
    else:
        income_tax_gross = b1_lim * b1_rate + (b2_lim - b1_lim) * b2_rate + (taxable_base - b2_lim) * b3_rate

    d1 = _decimal(tax_cfg.employment_deduction_band1_limit, "Employment deduction band 1 limit")
    d2 = _decimal(tax_cfg.employment_deduction_band2_limit, "Employment deduction band 2 limit")
    d3 = _decimal(tax_cfg.employment_deduction_band3_limit, "Employment deduction band 3 limit")
    floor = _decimal(tax_cfg.employment_deduction_floor, "Employment deduction floor")
    if taxable_base <= d1:
        raw_deduction = _decimal(tax_cfg.employment_deduction_band1_amount, "Employment deduction band 1 amount")
    elif taxable_base <= d2:
        raw_deduction = (
            _decimal(tax_cfg.employment_deduction_band2_base, "Employment deduction band 2 base")
            + _decimal(tax_cfg.employment_deduction_band2_variable, "Employment deduction band 2 variable")
            * (d2 - taxable_base) / _decimal(tax_cfg.employment_deduction_band2_range, "Employment deduction band 2 range")
        )
    elif taxable_base <= d3:
        raw_deduction = (
            _decimal(tax_cfg.employment_deduction_band3_base, "Employment deduction band 3 base")
            * (d3 - taxable_base) / _decimal(tax_cfg.employment_deduction_band3_range, "Employment deduction band 3 range")
        )
    else:
        raw_deduction = ZERO
    employment_deduction = max(raw_deduction, floor) if raw_deduction > ZERO else ZERO
    income_tax_net = max(ZERO, income_tax_gross - employment_deduction)
    regional_surtax = taxable_base * regional
    municipal_surtax = taxable_base * municipal
    net_annual = gross - social_security - employee - income_tax_net - regional_surtax - municipal_surtax
    if net_annual < ZERO:
        raise SalaryCalculationError("Computed net annual salary must not be negative")
    net_monthly = net_annual / salary_months
    if net_monthly < ZERO:
        raise SalaryCalculationError("Computed net monthly salary must not be negative")

    return SalaryBreakdown(
        gross_annual=float(_round(gross)), social_security=float(_round(social_security)),
        employee_pension_contribution_annual=float(_round(employee)),
        employer_pension_contribution_annual=float(_round(employer)),
        tfr_contribution_annual=float(_round(tfr)),
        pension_payroll_deduction_annual=float(_round(pension_effects.payroll_deduction)),
        pension_employer_taxable_excess_annual=float(_round(pension_effects.employer_taxable_excess)),
        pension_cap_eligible_contributions_annual=float(_round(employee + employer)),
        pension_cap_used_annual=float(_round(pension_effects.cap_used)),
        pension_cap_excess_annual=float(_round(pension_effects.cap_excess)),
        pension_deductibility_cap=float(_round(pension_effects.deductibility_cap)),
        pension_cap_scope=pension_effects.cap_scope,
        tax_config_id=pension_effects.tax_config_id,
        tax_config_valid_from=pension_effects.tax_config_valid_from,
        taxable_base=float(_round(taxable_base)), income_tax_gross=float(_round(income_tax_gross)),
        employment_deduction=float(_round(employment_deduction)), income_tax_net=float(_round(income_tax_net)),
        regional_surtax=float(_round(regional_surtax)), municipal_surtax=float(_round(municipal_surtax)),
        net_annual=float(_round(net_annual)), computed_net_monthly=float(_round(net_monthly)),
        meal_vouchers_monthly=float(_round(meal_vouchers / 12)), welfare_monthly=float(_round(welfare / 12)),
        salary_months=salary_months,
    )
