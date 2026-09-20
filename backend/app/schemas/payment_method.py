import datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.services.billing import BANK_FUNDED_CARD_TYPES

PaymentMethodType = Literal["bank", "debit_card", "credit_card", "revolving", "prepaid", "cash"]


class PaymentMethodCreate(BaseModel):
    name: str
    type: PaymentMethodType
    linked_bank_id: Optional[str] = None
    opening_balance: Optional[Decimal] = Field(None, ge=0, max_digits=12, decimal_places=2)
    has_stamp_duty: bool = False

    @model_validator(mode="after")
    def require_linked_bank_for_bank_funded_cards(self):
        if self.type in BANK_FUNDED_CARD_TYPES and self.linked_bank_id is None:
            raise ValueError("linked_bank_id is required for bank-funded card payment methods")
        return self


class PaymentMethodUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None
    linked_bank_id: Optional[str] = None
    effective_billing_month: Optional[str] = None
    has_stamp_duty: Optional[bool] = None

    @field_validator("effective_billing_month")
    @classmethod
    def validate_effective_billing_month(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            raise ValueError("effective_billing_month must be YYYY-MM-DD")
        try:
            parsed = datetime.date.fromisoformat(value)
        except ValueError:
            raise ValueError("effective_billing_month must be YYYY-MM-DD")
        if value != parsed.isoformat():
            raise ValueError("effective_billing_month must be YYYY-MM-DD")
        if parsed.day != 1:
            raise ValueError("effective_billing_month must be the first day of a month")
        return value

    @model_validator(mode="after")
    def require_effective_period_for_link_change(self):
        fields = self.model_fields_set
        if "linked_bank_id" in fields and "effective_billing_month" not in fields:
            raise ValueError("effective_billing_month is required when changing linked_bank_id")
        if "effective_billing_month" in fields and "linked_bank_id" not in fields:
            raise ValueError("effective_billing_month requires linked_bank_id")
        return self


class SetMainBankRequest(BaseModel):
    opening_balance: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
