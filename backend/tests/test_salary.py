import pytest
from dataclasses import dataclass
from app.services.salary import calculate_salary

@dataclass
class MockSalaryCfg:
    ral: float
    employer_contrib_rate: float = 0.04
    voluntary_contrib_rate: float = 0.02
    regional_tax_rate: float = 0.0173
    municipal_tax_rate: float = 0.008
    meal_vouchers_annual: float = 1200
    welfare_annual: float = 0

@dataclass
class MockTaxCfg:
    inps_rate: float = 0.0919
    irpef_band1_rate: float = 0.23
    irpef_band1_limit: float = 28000
    irpef_band2_rate: float = 0.33
    irpef_band2_limit: float = 50000
    irpef_band3_rate: float = 0.43
    employment_deduction_band1_limit: float = 15000
    employment_deduction_band1_amount: float = 1955
    employment_deduction_band2_limit: float = 28000
    employment_deduction_band2_base: float = 1910
    employment_deduction_band2_variable: float = 1190
    employment_deduction_band2_range: float = 13000
    employment_deduction_band3_limit: float = 50000
    employment_deduction_band3_base: float = 1910
    employment_deduction_band3_range: float = 22000
    pension_deductibility_cap: float = 5300.00
    employment_deduction_floor: float = 690.00

def test_inps_computed_correctly():
    b = calculate_salary(MockSalaryCfg(ral=42000), MockTaxCfg())
    assert b.social_security == pytest.approx(42000 * 0.0919, rel=1e-4)

def test_deductible_below_cap():
    b = calculate_salary(MockSalaryCfg(ral=42000, employer_contrib_rate=0.04, voluntary_contrib_rate=0.02), MockTaxCfg())
    assert b.pension_deductible == pytest.approx(42000 * 0.06, rel=1e-4)

def test_deductible_capped():
    b = calculate_salary(MockSalaryCfg(ral=42000, employer_contrib_rate=0.15, voluntary_contrib_rate=0.05), MockTaxCfg())
    assert b.pension_deductible == pytest.approx(5300.00, rel=1e-3)

def test_irpef_first_band_only():
    b = calculate_salary(MockSalaryCfg(ral=24000, employer_contrib_rate=0, voluntary_contrib_rate=0), MockTaxCfg())
    assert b.income_tax_gross == pytest.approx(b.taxable_base * 0.23, rel=1e-3)

def test_irpef_crosses_into_band2():
    b = calculate_salary(MockSalaryCfg(ral=38000, employer_contrib_rate=0, voluntary_contrib_rate=0), MockTaxCfg())
    expected = 28000 * 0.23 + (b.taxable_base - 28000) * 0.33
    assert b.income_tax_gross == pytest.approx(expected, rel=1e-3)

def test_irpef_netto_never_negative():
    b = calculate_salary(MockSalaryCfg(ral=8000, employer_contrib_rate=0, voluntary_contrib_rate=0), MockTaxCfg())
    assert b.income_tax_net >= 0

def test_netto_mensile_is_annual_div_12():
    b = calculate_salary(MockSalaryCfg(ral=42000), MockTaxCfg())
    # net_monthly is rounded to 2dp; check within rounding tolerance
    assert b.net_monthly == pytest.approx(round(b.net_annual / 12, 2), abs=0.01)

def test_meal_vouchers_excluded_from_netto_mensile():
    b1 = calculate_salary(MockSalaryCfg(ral=42000, meal_vouchers_annual=0), MockTaxCfg())
    b2 = calculate_salary(MockSalaryCfg(ral=42000, meal_vouchers_annual=2400), MockTaxCfg())
    assert b1.net_monthly == pytest.approx(b2.net_monthly, rel=1e-6)
    assert b2.meal_vouchers_monthly == pytest.approx(200.0)

def test_salary_api_calculate_returns_breakdown(client):
    client.post("/api/v1/auth/register", json={
        "email": "alice@example.com", "password": "Password1!", "name": "Alice"
    })
    r = client.get("/api/v1/salary/calculate", params={
        "as_of": "2026-01-01", "ral": 42000,
        "employer_contrib_rate": 0.04, "voluntary_contrib_rate": 0.02,
        "regional_tax_rate": 0.0173, "municipal_tax_rate": 0.008,
    })
    assert r.status_code == 200
    assert r.json()["net_monthly"] > 0
