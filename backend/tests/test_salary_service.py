import pytest
from app.services.salary import SalaryCalculationError, calculate_salary, SalaryBreakdown


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
    ral = 30000.0
    employer_contrib_rate = 0.02
    voluntary_contrib_rate = 0.01
    regional_tax_rate = 0.0173
    municipal_tax_rate = 0.001
    meal_vouchers_annual = 1200.0
    welfare_annual = 0.0
    salary_months = 12


def test_breakdown_uses_english_field_names():
    result = calculate_salary(_Salary(), _Tax())
    # New English names must exist
    assert hasattr(result, "gross_annual")
    assert hasattr(result, "social_security")
    assert hasattr(result, "pension_deductible")
    assert hasattr(result, "taxable_base")
    assert hasattr(result, "income_tax_gross")
    assert hasattr(result, "employment_deduction")
    assert hasattr(result, "income_tax_net")
    assert hasattr(result, "regional_surtax")
    assert hasattr(result, "municipal_surtax")
    assert hasattr(result, "net_annual")
    assert hasattr(result, "net_monthly")
    # Old Italian names must NOT exist
    assert not hasattr(result, "ral")
    assert not hasattr(result, "inps")
    assert not hasattr(result, "imponibile")
    assert not hasattr(result, "irpef_lordo")
    assert not hasattr(result, "netto_mensile")


def test_salary_months_13_divides_net_annual_by_13():
    class _Sal13(_Salary):
        salary_months = 13
    result = calculate_salary(_Sal13(), _Tax())
    assert abs(result.net_monthly - result.net_annual / 13) < 0.01


def test_salary_months_14_divides_by_14():
    class _Sal14(_Salary):
        salary_months = 14
    result = calculate_salary(_Sal14(), _Tax())
    assert abs(result.net_monthly - result.net_annual / 14) < 0.01


def test_meal_vouchers_always_divide_by_12_regardless_of_salary_months():
    class _Sal13(_Salary):
        salary_months = 13
    result = calculate_salary(_Sal13(), _Tax())
    assert abs(result.meal_vouchers_monthly - 1200.0 / 12) < 0.01


def test_employment_deduction_floor_applied_near_50k():
    """Near €50k taxable base the formula gives less than €690; floor must kick in.

    At ral=52000, taxable base ≈ 52000 - (52000*0.0919) - (52000*0.03) = ~46,600
    which lands in band 3 where formula = 1910*(50000-46600)/22000 ≈ 295 < 690.
    The floor must push it back to 690.
    """
    class _NearCeilingSalary(_Salary):
        ral = 52000.0
    result = calculate_salary(_NearCeilingSalary(), _Tax())
    assert result.employment_deduction > 0, "expected positive deduction for this income level"
    assert result.employment_deduction >= 690.0


def test_employment_deduction_zero_above_50k():
    """Above €50k taxable base the deduction is zero — floor does NOT create a deduction."""
    class _VeryHighSalary(_Salary):
        ral = 80000.0
    result = calculate_salary(_VeryHighSalary(), _Tax())
    assert result.employment_deduction == 0.0


def test_pension_deductible_capped():
    class _HighPension(_Salary):
        employer_contrib_rate = 0.10
        voluntary_contrib_rate = 0.10
        ral = 60000.0
    result = calculate_salary(_HighPension(), _Tax())
    assert result.pension_deductible == pytest.approx(5300.0)


def test_calculation_uses_decimal_golden_values():
    """Independent hand calculation for the standard 2026 tax table."""
    result = calculate_salary(_Salary(), _Tax())

    assert result.social_security == 2757.00
    assert result.pension_deductible == 900.00
    assert result.income_tax_gross == 6058.89
    assert result.net_monthly == 1871.98


def test_legacy_invalid_tax_config_raises_controlled_error():
    class _UnsafeTax(_Tax):
        employment_deduction_band2_range = 0

    with pytest.raises(SalaryCalculationError, match="ranges must be positive"):
        calculate_salary(_Salary(), _UnsafeTax())


def test_contributions_cannot_produce_negative_taxable_base():
    class _ExcessiveContributions(_Salary):
        ral = 100
        employer_contrib_rate = 1
        voluntary_contrib_rate = 1
        regional_tax_rate = 1
        municipal_tax_rate = 1

    with pytest.raises(SalaryCalculationError, match="contributions must not exceed"):
        calculate_salary(_ExcessiveContributions(), _Tax())


def test_capped_pension_deduction_that_produces_negative_net_raises():
    class _FullVoluntaryContribution(_Salary):
        ral = 36000
        employer_contrib_rate = 0
        voluntary_contrib_rate = 1
        regional_tax_rate = 0
        municipal_tax_rate = 0

    with pytest.raises(SalaryCalculationError, match="Computed net annual salary"):
        calculate_salary(_FullVoluntaryContribution(), _Tax())


def test_zero_taxable_base_is_allowed_at_contribution_boundary():
    class _BoundaryContributions(_Salary):
        ral = 100
        employer_contrib_rate = 0.9081
        voluntary_contrib_rate = 0

    result = calculate_salary(_BoundaryContributions(), _Tax())

    assert result.taxable_base == 0
    assert result.regional_surtax == 0
    assert result.municipal_surtax == 0


def test_net_monthly_is_rounded_to_2dp():
    """net_monthly must be rounded to 2 decimal places."""
    from app.services.salary import calculate_salary
    from unittest.mock import MagicMock

    salary_cfg = MagicMock()
    salary_cfg.ral = 36000
    salary_cfg.employer_contrib_rate = 0.0693
    salary_cfg.voluntary_contrib_rate = 0.02
    salary_cfg.regional_tax_rate = 0.0123
    salary_cfg.municipal_tax_rate = 0.008
    salary_cfg.salary_months = 13   # forces non-terminating division
    salary_cfg.meal_vouchers_annual = 0
    salary_cfg.welfare_annual = 0

    tax_cfg = MagicMock()
    tax_cfg.inps_rate = 0.0919
    tax_cfg.irpef_band1_rate = 0.23
    tax_cfg.irpef_band1_limit = 28000
    tax_cfg.irpef_band2_rate = 0.33
    tax_cfg.irpef_band2_limit = 50000
    tax_cfg.irpef_band3_rate = 0.43
    tax_cfg.pension_deductibility_cap = 5300
    tax_cfg.employment_deduction_band1_limit = 15000
    tax_cfg.employment_deduction_band1_amount = 1955
    tax_cfg.employment_deduction_band2_limit = 28000
    tax_cfg.employment_deduction_band2_base = 1910
    tax_cfg.employment_deduction_band2_variable = 1190
    tax_cfg.employment_deduction_band2_range = 13000
    tax_cfg.employment_deduction_band3_limit = 50000
    tax_cfg.employment_deduction_band3_base = 1910
    tax_cfg.employment_deduction_band3_range = 22000
    tax_cfg.employment_deduction_floor = 690

    result = calculate_salary(salary_cfg, tax_cfg)
    # Must have exactly 2 decimal places (no trailing float noise)
    assert result.net_monthly == round(result.net_monthly, 2)
    assert len(str(result.net_monthly).split(".")[-1]) <= 2
