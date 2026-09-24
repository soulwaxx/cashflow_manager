from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ForecastCreate(BaseModel):
    name: str
    base_year: int = Field(ge=2000, le=2100)
    projection_years: int = Field(ge=1, le=10)


class ForecastUpdate(BaseModel):
    name: str | None = None
    projection_years: int | None = Field(default=None, ge=1, le=10)


class ForecastLineCreate(BaseModel):
    detail: str = Field(min_length=1)
    base_amount: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    category_id: str | None = None
    payment_method_id: str | None = None
    billing_day: int = Field(default=1, ge=1, le=31)
    notes: str | None = None

    @field_validator("detail")
    @classmethod
    def nonblank_detail(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("detail must not be blank")
        return value


class AdjustmentDate(BaseModel):
    valid_from: str

    @field_validator("valid_from")
    @classmethod
    def month_start(cls, value: str) -> str:
        if not re.fullmatch(r"\d{4}-\d{2}-01", value):
            raise ValueError("valid_from must be a first-of-month YYYY-MM-01 date")
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("valid_from must be a valid month") from exc
        return value


class AdjustmentCreate(AdjustmentDate):
    new_amount: Decimal = Field(ge=-100, max_digits=12, decimal_places=2)
    adjustment_type: Literal["fixed", "percentage"] = "fixed"

    @model_validator(mode="after")
    def validate_fixed_amount(self) -> AdjustmentCreate:
        if self.adjustment_type == "fixed" and self.new_amount < 0:
            raise ValueError("fixed adjustment amount must not be negative")
        return self


class AdjustmentUpdate(BaseModel):
    valid_from: str | None = None
    new_amount: Decimal | None = Field(default=None, ge=-100, max_digits=12, decimal_places=2)
    adjustment_type: Literal["fixed", "percentage"] | None = None

    @field_validator("valid_from")
    @classmethod
    def month_start(cls, value: str | None) -> str | None:
        return AdjustmentDate(valid_from=value).valid_from if value is not None else None


class ForecastRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    name: str
    base_year: int
    projection_years: int
    created_at: datetime
    updated_at: datetime


class ForecastAdjustmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    valid_from: str
    new_amount: float
    adjustment_type: Literal["fixed", "percentage"]


class ForecastAdjustmentCreated(ForecastAdjustmentRead):
    forecast_line_id: str


class ForecastLineRead(BaseModel):
    id: str
    source_transaction_id: str | None
    detail: str
    category_id: str | None
    base_amount: float
    billing_day: int
    payment_method_id: str | None
    notes: str | None
    adjustments: list[ForecastAdjustmentRead]


class ForecastDetail(ForecastRead):
    lines: list[ForecastLineRead]


class ForecastMonth(BaseModel):
    month: str
    effective_amount: float


class ForecastProjectedLine(BaseModel):
    line_id: str
    detail: str
    category_id: str | None
    base_amount: float
    billing_day: int
    adjustments: list[ForecastAdjustmentRead]
    months: list[ForecastMonth]


class ForecastMonthlyTotal(BaseModel):
    month: str
    total: float


class ForecastYearlyTotal(BaseModel):
    year: int
    total: float


class ForecastPeriod(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from")
    to: str


class ForecastProjectionRead(BaseModel):
    forecast_id: str
    base_year: int
    projection_years: int
    period: ForecastPeriod
    lines: list[ForecastProjectedLine]
    monthly_totals: list[ForecastMonthlyTotal]
    yearly_totals: list[ForecastYearlyTotal]
