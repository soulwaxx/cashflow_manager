from __future__ import annotations

import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class _SalaryFields(BaseModel):
    ral: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    employer_contrib_rate: Decimal = Field(Decimal("0"), ge=0, le=1, max_digits=6, decimal_places=4)
    voluntary_contrib_rate: Decimal = Field(Decimal("0"), ge=0, le=1, max_digits=6, decimal_places=4)
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
            raise ValueError("Effective period must be YYYY-MM-DD")
        if value != parsed.isoformat() or parsed.day != 1:
            raise ValueError("Effective period must be the first day of a month")
        return parsed.isoformat()


class SalaryConfigCreate(_SalaryFields, _EffectivePeriod):
    valid_from: str
    manual_net_override: Decimal | None = Field(
        default=None, ge=0, max_digits=10, decimal_places=2
    )

    @field_validator("valid_from")
    @classmethod
    def validate_valid_from(cls, value: str) -> str:
        return cls._validate_effective_period(value)


class SalaryCalculationRequest(_SalaryFields, _EffectivePeriod):
    as_of: str

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: str) -> str:
        return cls._validate_effective_period(value)
