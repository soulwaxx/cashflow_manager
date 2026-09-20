from __future__ import annotations
import datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

AccountType = Literal["bank", "saving", "investment", "pension"]


def _validate_iso_date(v: str) -> str:
    try:
        datetime.date.fromisoformat(v)
    except ValueError:
        raise ValueError(f"Invalid date format: {v!r} (expected YYYY-MM-DD)")
    return v


class TransferCreate(BaseModel):
    date: str
    detail: str = ""
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    from_account_type: AccountType
    from_account_id: Optional[str] = None
    # Name fields are accepted only as a bounded compatibility input. New clients
    # submit stable IDs, while the server snapshots the resolved current name.
    from_account_name: Optional[str] = Field(None, max_length=255)
    to_account_type: AccountType
    to_account_id: Optional[str] = None
    to_account_name: Optional[str] = Field(None, max_length=255)
    recurrence_months: Optional[int] = Field(None, ge=1, le=60)
    notes: Optional[str] = None

    @field_validator("date")
    @classmethod
    def validate_date(cls, v: str) -> str:
        return _validate_iso_date(v)

    @field_validator("from_account_name", "to_account_name")
    @classmethod
    def validate_account_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Account name must not be blank")
        return value

    @model_validator(mode="after")
    def validate_endpoints(self) -> TransferCreate:
        for prefix in ("from", "to"):
            if not getattr(self, f"{prefix}_account_id") and not getattr(self, f"{prefix}_account_name"):
                raise ValueError(f"{prefix}_account_id is required")
        if (
            self.from_account_type == self.to_account_type
            and self.from_account_id is not None
            and self.from_account_id == self.to_account_id
        ):
            raise ValueError("Transfer endpoints must be different accounts")
        if (
            self.from_account_type == self.to_account_type
            and self.from_account_id is None
            and self.to_account_id is None
            and self.from_account_name == self.to_account_name
        ):
            raise ValueError("Transfer endpoints must be different accounts")
        return self


class TransferUpdate(BaseModel):
    date: Optional[str] = None
    detail: Optional[str] = None
    amount: Optional[Decimal] = Field(None, gt=0, max_digits=12, decimal_places=2)
    notes: Optional[str] = None

    @field_validator("date")
    @classmethod
    def validate_date(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _validate_iso_date(v)
