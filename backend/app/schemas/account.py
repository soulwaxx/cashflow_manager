from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


AccountType = Literal["saving", "investment", "pension"]


class AccountCreate(BaseModel):
    type: AccountType
    name: str = Field(min_length=1, max_length=255)
    opening_balance: Decimal = Field(Decimal("0"), ge=0, max_digits=12, decimal_places=2)
    opening_balance_month: str | None = None

    @field_validator("opening_balance_month")
    @classmethod
    def canonical_opening_month(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            raise ValueError("Opening balance month must be YYYY-MM-01") from None
        if parsed.isoformat() != value or parsed.day != 1:
            raise ValueError("Opening balance month must be YYYY-MM-01")
        return value

    @model_validator(mode="after")
    def require_pension_month(self):
        if self.type == "pension" and self.opening_balance_month is None:
            raise ValueError("Pension accounts require an opening balance month")
        if self.type != "pension" and self.opening_balance_month is not None:
            raise ValueError("Only pension accounts accept an opening balance month")
        return self

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name must not be blank")
        return value
