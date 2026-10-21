from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.pension import PensionComponents, PensionPayrollEffects
from app.services.salary import SalaryCalculationError, calculate_salary


class _Tax:
    inps_rate = 0.0919
    irpef_band1_rate = 0.23
    irpef_band1_limit = 28000
    irpef_band2_rate = 0.33
    irpef_band2_limit = 50000
    irpef_band3_rate = 0.43
    employment_deduction_band1_limit = 15000
    employment_deduction_band1_amount = 1955
    employment_deduction_band2_limit = 28000
    employment_deduction_band2_base = 1910
    employment_deduction_band2_variable = 1190
    employment_deduction_band2_range = 13000
    employment_deduction_band3_limit = 50000
    employment_deduction_band3_base = 1910
    employment_deduction_band3_range = 22000
    pension_deductibility_cap = 5300.00
    employment_deduction_floor = 690.00


class _Salary:
    ral = Decimal("30000")
    regional_tax_rate = Decimal("0.0173")
    municipal_tax_rate = Decimal("0.001")
    meal_vouchers_annual = Decimal("1200")
    welfare_annual = Decimal("0")
    salary_months = 12


def _salary_values(**overrides):
    values = {key: value for key, value in _Salary.__dict__.items() if not key.startswith("__")}
    values.update(overrides)
    return SimpleNamespace(**values)


def _tax_values(**overrides):
    values = {key: value for key, value in _Tax.__dict__.items() if not key.startswith("__")}
    values.update(overrides)
    return SimpleNamespace(**values)


def _effects(employee="0", employer="0", tfr="0", cap="5300"):
    employee, employer, tfr, cap = map(Decimal, (employee, employer, tfr, cap))
    eligible = employee + employer
    used = min(eligible, cap)
    deduction = min(employee, max(cap - employer, Decimal("0")))
    excess = max(employer - cap, Decimal("0"))
    return PensionPayrollEffects(
        PensionComponents(employee, employer, tfr), cap, used,
        max(eligible - cap, Decimal("0")), deduction, excess,
        "tax-id", "2026-01-01",
    )


def test_salary_breakdown_exposes_explicit_pension_effects_not_ambiguous_field():
    result = calculate_salary(_Salary(), _Tax(), _effects("300", "600", "2400"))
    assert result.gross_annual == 30000
    assert result.employee_pension_contribution_annual == 300
    assert result.employer_pension_contribution_annual == 600
    assert result.tfr_contribution_annual == 2400
    assert result.pension_payroll_deduction_annual == 300
    assert result.pension_cap_used_annual == 900
    assert result.tax_config_valid_from == "2026-01-01"
    assert not hasattr(result, "pension_deductible")


def test_net_payment_average_tracks_salary_month_count():
    result12 = calculate_salary(_Salary(), _Tax(), _effects())
    result13 = calculate_salary(_salary_values(salary_months=13), _Tax(), _effects())
    result14 = calculate_salary(_salary_values(salary_months=14), _Tax(), _effects())
    assert result12.computed_net_monthly > result13.computed_net_monthly > result14.computed_net_monthly
    assert result13.salary_months == 13
    assert result14.salary_months == 14


def test_meal_vouchers_always_divide_by_12():
    salary = _salary_values(salary_months=13)
    assert calculate_salary(salary, _Tax(), _effects()).meal_vouchers_monthly == 100


def test_employer_only_excess_increases_taxable_base_without_cash_deduction():
    effects = _effects("0", "6000", "2400")
    result = calculate_salary(_Salary(), _Tax(), effects)
    assert result.pension_payroll_deduction_annual == 0
    assert result.pension_employer_taxable_excess_annual == 700
    assert result.taxable_base == pytest.approx(30000 + 6000 - 2757 - 5300)
    assert result.tfr_contribution_annual == 2400


def test_employment_deduction_floor_and_ceiling_are_preserved():
    near = _salary_values(ral=52000)
    high = _salary_values(ral=80000)
    assert calculate_salary(near, _Tax(), _effects()).employment_deduction >= 690
    assert calculate_salary(high, _Tax(), _effects()).employment_deduction == 0


def test_raw_fractional_cent_pension_input_is_rounded_only_for_final_outputs():
    salary = _salary_values(ral=Decimal("10000"), regional_tax_rate=Decimal("0"),
                            municipal_tax_rate=Decimal("0"))
    tax = _tax_values(
        inps_rate=Decimal("0"), irpef_band1_rate=Decimal("0.23"),
        employment_deduction_band1_limit=Decimal("1"),
        employment_deduction_band2_limit=Decimal("2"),
        employment_deduction_band3_limit=Decimal("3"),
        employment_deduction_band1_amount=Decimal("0"),
        employment_deduction_floor=Decimal("0"),
    )
    effects = _effects("0.015", "0")
    result = calculate_salary(salary, tax, effects)
    assert result.employee_pension_contribution_annual == 0.02
    assert result.net_annual == 7699.99


def test_invalid_tax_config_raises_controlled_error():
    unsafe = SimpleNamespace(**{**_Tax.__dict__, "employment_deduction_band2_range": 0})
    with pytest.raises(SalaryCalculationError, match="ranges must be positive"):
        calculate_salary(_Salary(), unsafe, _effects())


def test_salary_without_explicit_pension_has_no_implicit_contribution():
    result = calculate_salary(_Salary(), _Tax())
    assert result.employee_pension_contribution_annual == 0
    assert result.employer_pension_contribution_annual == 0
    assert result.pension_cap_used_annual == 0
