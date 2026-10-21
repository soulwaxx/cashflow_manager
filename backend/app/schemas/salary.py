from __future__ import annotations

import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator


class _SalaryFields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ral: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    regional_tax_rate: Decimal = Field(Decimal("0"), ge=0, le=1, max_digits=6, decimal_places=4)
    municipal_tax_rate: Decimal = Field(Decimal("0"), ge=0, le=1, max_digits=6, decimal_places=4)
    meal_vouchers_annual: Decimal = Field(Decimal("0"), ge=0, max_digits=10, decimal_places=2)
    welfare_annual: Decimal = Field(Decimal("0"), ge=0, max_digits=10, decimal_places=2)
    salary_months: int = Field(12, ge=12, le=14)


class _EffectivePeriod:
    @staticmethod
    def _validate_effective_period(value: str) -> str:
        try:
            parsed = datetime.date.fromisoformat(value)
        except ValueError:
            raise ValueError("Effective period must be YYYY-MM-DD") from None
        if value != parsed.isoformat() or parsed.day != 1:
            raise ValueError("Effective period must be the first day of a month")
        return parsed.isoformat()


class SalaryConfigCreate(_SalaryFields, _EffectivePeriod):
    valid_from: str
    manual_net_override: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)

    @field_validator("valid_from")
    @classmethod
    def validate_valid_from(cls, value: str) -> str:
        return cls._validate_effective_period(value)


class SalaryPreviewFields(_SalaryFields):
    pass


class PensionPayrollRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: str | None = Field(default=None, min_length=1, max_length=36)
    employee_contrib_rate: Decimal = Field(Decimal("0"), ge=0, le=1, max_digits=6, decimal_places=4)
    employee_contrib_annual_base: Decimal = Field(Decimal("0"), ge=0, max_digits=12, decimal_places=2)
    employer_contrib_rate: Decimal = Field(Decimal("0"), ge=0, le=1, max_digits=6, decimal_places=4)
    employer_contrib_annual_base: Decimal = Field(Decimal("0"), ge=0, max_digits=12, decimal_places=2)
    tfr_contrib_annual: Decimal = Field(Decimal("0"), ge=0, max_digits=12, decimal_places=2)


class SalaryCalculationRequest(BaseModel, _EffectivePeriod):
    model_config = ConfigDict(extra="forbid")
    as_of: str
    salary: SalaryPreviewFields
    pension: PensionPayrollRequest | None

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: str) -> str:
        return cls._validate_effective_period(value)


class PensionPayrollBreakdown(BaseModel):
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


class SalaryBreakdownResponse(BaseModel):
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
    calculated_as_of: str | None = None
    salary_config_id: str | None = None
    salary_config_valid_from: str | None = None
    pension_config_id: str | None = None
    pension_config_valid_from: str | None = None
    manual_net_override: float | None = None
    effective_net_monthly: float | None = None


class SalaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    user_id: str
    valid_from: str
    ral: float
    regional_tax_rate: float
    municipal_tax_rate: float
    meal_vouchers_annual: float
    welfare_annual: float
    salary_months: int
    manual_net_override: float | None
    computed_net_monthly: float
    effective_net_monthly: float
    calculated_as_of: str
    salary_config_id: str
    salary_config_valid_from: str
    pension_config_id: str | None
    pension_config_valid_from: str | None
    pension: PensionPayrollBreakdown
    tax_config_id: str
    tax_config_valid_from: str
