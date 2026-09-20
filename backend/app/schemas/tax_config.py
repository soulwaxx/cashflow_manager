from __future__ import annotations

import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator


class TaxConfigCreate(BaseModel):
    valid_from: str
    inps_rate: Decimal = Field(Decimal("0.0919"), ge=0, le=1, max_digits=6, decimal_places=4)
    irpef_band1_rate: Decimal = Field(Decimal("0.23"), ge=0, le=1, max_digits=6, decimal_places=4)
    irpef_band1_limit: Decimal = Field(Decimal("28000"), gt=0, max_digits=10, decimal_places=2)
    irpef_band2_rate: Decimal = Field(Decimal("0.33"), ge=0, le=1, max_digits=6, decimal_places=4)
    irpef_band2_limit: Decimal = Field(Decimal("50000"), gt=0, max_digits=10, decimal_places=2)
    irpef_band3_rate: Decimal = Field(Decimal("0.43"), ge=0, le=1, max_digits=6, decimal_places=4)
    employment_deduction_band1_limit: Decimal = Field(Decimal("15000"), gt=0, max_digits=10, decimal_places=2)
    employment_deduction_band1_amount: Decimal = Field(Decimal("1955"), ge=0, max_digits=10, decimal_places=2)
    employment_deduction_band2_limit: Decimal = Field(Decimal("28000"), gt=0, max_digits=10, decimal_places=2)
    employment_deduction_band2_base: Decimal = Field(Decimal("1910"), ge=0, max_digits=10, decimal_places=2)
    employment_deduction_band2_variable: Decimal = Field(Decimal("1190"), ge=0, max_digits=10, decimal_places=2)
    employment_deduction_band2_range: Decimal = Field(Decimal("13000"), gt=0, max_digits=10, decimal_places=2)
    employment_deduction_band3_limit: Decimal = Field(Decimal("50000"), gt=0, max_digits=10, decimal_places=2)
    employment_deduction_band3_base: Decimal = Field(Decimal("1910"), ge=0, max_digits=10, decimal_places=2)
    employment_deduction_band3_range: Decimal = Field(Decimal("22000"), gt=0, max_digits=10, decimal_places=2)
    pension_deductibility_cap: Decimal = Field(Decimal("5300"), ge=0, max_digits=10, decimal_places=2)
    employment_deduction_floor: Decimal = Field(Decimal("690"), ge=0, max_digits=10, decimal_places=2)

    @field_validator("valid_from")
    @classmethod
    def validate_valid_from(cls, value: str) -> str:
        try:
            parsed = datetime.date.fromisoformat(value)
        except ValueError:
            raise ValueError("Effective period must be YYYY-MM-DD")
        if value != parsed.isoformat() or parsed.day != 1:
            raise ValueError("Effective period must be the first day of a month")
        return parsed.isoformat()

    @model_validator(mode="after")
    def validate_threshold_order(self) -> TaxConfigCreate:
        if self.irpef_band1_limit >= self.irpef_band2_limit:
            raise ValueError("IRPEF band 1 limit must be below band 2 limit")
        if not (
            self.employment_deduction_band1_limit
            < self.employment_deduction_band2_limit
            < self.employment_deduction_band3_limit
        ):
            raise ValueError("Employment deduction band limits must be strictly increasing")
        return self
