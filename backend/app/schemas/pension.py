from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_serializer, field_validator


PensionSnapshotSource = Literal["statement", "manual", "legacy_override"]


def _canonical_month(value: str) -> str:
    try:
        parsed = datetime.date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError("Month must be a canonical YYYY-MM-01 date") from None
    if value != parsed.isoformat() or parsed.day != 1:
        raise ValueError("Month must be a canonical YYYY-MM-01 date")
    return parsed.isoformat()


def _finite_decimal(value: Decimal) -> Decimal:
    if not value.is_finite():
        raise ValueError("Value must be finite")
    return value


class PensionConfigFields(BaseModel):
    account_id: str = Field(min_length=1, max_length=36)
    valid_from: str
    employee_contrib_rate: Decimal = Field(ge=0, le=1, max_digits=6, decimal_places=4)
    employee_contrib_annual_base: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    employer_contrib_rate: Decimal = Field(ge=0, le=1, max_digits=6, decimal_places=4)
    employer_contrib_annual_base: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    tfr_contrib_annual: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    contribution_periods_by_month: list[StrictInt] = Field(min_length=12, max_length=12)

    @field_validator("valid_from")
    @classmethod
    def validate_valid_from(cls, value: str) -> str:
        return _canonical_month(value)

    @field_validator(
        "employee_contrib_rate",
        "employee_contrib_annual_base",
        "employer_contrib_rate",
        "employer_contrib_annual_base",
        "tfr_contrib_annual",
    )
    @classmethod
    def validate_finite_values(cls, value: Decimal) -> Decimal:
        return _finite_decimal(value)

    @field_validator("contribution_periods_by_month")
    @classmethod
    def validate_calendar_weights(cls, value: list[int]) -> list[int]:
        if any(type(weight) is not int or weight < 0 for weight in value):
            raise ValueError("Calendar weights must be nonnegative integers")
        if sum(value) <= 0:
            raise ValueError("At least one calendar weight must be positive")
        return value


class PensionConfigCreate(PensionConfigFields):
    pass


class PensionConfigResponse(PensionConfigFields):
    model_config = ConfigDict(from_attributes=True)
    id: str
    user_id: str

    @field_serializer(
        "employee_contrib_rate",
        "employee_contrib_annual_base",
        "employer_contrib_rate",
        "employer_contrib_annual_base",
        "tfr_contrib_annual",
        when_used="json",
    )
    def serialize_numeric_json(self, value: Decimal) -> float:
        return float(value)


class PensionBalanceSnapshotCreate(BaseModel):
    account_id: str = Field(min_length=1, max_length=36)
    as_of_month: str
    balance: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    source: Literal["statement", "manual"]
    notes: str | None = None

    @field_validator("as_of_month")
    @classmethod
    def validate_as_of_month(cls, value: str) -> str:
        return _canonical_month(value)

    @field_validator("balance")
    @classmethod
    def validate_finite_balance(cls, value: Decimal) -> Decimal:
        return _finite_decimal(value)


class PensionBalanceSnapshotResponse(PensionBalanceSnapshotCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    user_id: str
    source: PensionSnapshotSource

    @field_serializer("balance", when_used="json")
    def serialize_balance_json(self, value: Decimal) -> float:
        return float(value)


class PensionAccountResponse(BaseModel):
    id: str
    user_id: str
    type: Literal["pension"]
    name: str
    opening_balance: float
    opening_balance_month: str
    is_active: bool


class PensionYtdFlows(BaseModel):
    employee: float
    employer: float
    tfr: float


class PensionAnnualizedSummary(BaseModel):
    employee: float
    employer: float
    tfr: float
    eligible_contributions: float
    cap_used: float
    cap_excess: float
    cap: float
    cap_scope: str
    tax_config_valid_from: str


class PensionSummaryResponse(BaseModel):
    year: int
    as_of: str
    config: PensionConfigResponse | None
    year_to_date: PensionYtdFlows
    annualized: PensionAnnualizedSummary
