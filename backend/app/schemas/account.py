from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator


AccountType = Literal["saving", "investment"]


class AccountCreate(BaseModel):
    type: AccountType
    name: str = Field(min_length=1, max_length=255)
    opening_balance: Decimal = Field(Decimal("0"), ge=0, max_digits=12, decimal_places=2)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name must not be blank")
        return value
