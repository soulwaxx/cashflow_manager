from __future__ import annotations

import datetime
import re
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.payment_method import BANK_FUNDED_CARD_TYPES, PaymentMethodType


class _NamedInput(BaseModel):
    name: str = Field(min_length=1, max_length=255)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name must not be blank")
        return value


class MainBankIn(_NamedInput):
    opening_balance: Decimal = Field(Decimal("0"), ge=0, max_digits=12, decimal_places=2)


class AdditionalBankIn(_NamedInput):
    opening_balance: Decimal = Field(Decimal("0"), ge=0, max_digits=12, decimal_places=2)


class PaymentMethodIn(_NamedInput):
    type: PaymentMethodType
    linked_bank_name: Optional[str] = Field(None, min_length=1, max_length=255)
    opening_balance: Optional[Decimal] = Field(None, ge=0, max_digits=12, decimal_places=2)

    @field_validator("linked_bank_name")
    @classmethod
    def strip_linked_bank_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Linked bank name must not be blank")
        return value


class SavingAccountIn(_NamedInput):
    opening_balance: Decimal = Field(Decimal("0"), ge=0, max_digits=12, decimal_places=2)


class InvestmentAccountIn(_NamedInput):
    opening_balance: Decimal = Field(Decimal("0"), ge=0, max_digits=12, decimal_places=2)


class SalaryIn(BaseModel):
    ral: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    employer_contrib_rate: Decimal = Field(Decimal("0"), ge=0, le=1, max_digits=6, decimal_places=4)
    voluntary_contrib_rate: Decimal = Field(Decimal("0"), ge=0, le=1, max_digits=6, decimal_places=4)
    regional_tax_rate: Decimal = Field(Decimal("0"), ge=0, le=1, max_digits=6, decimal_places=4)
    municipal_tax_rate: Decimal = Field(Decimal("0"), ge=0, le=1, max_digits=6, decimal_places=4)
    meal_vouchers_annual: Decimal = Field(Decimal("0"), ge=0, max_digits=10, decimal_places=2)
    welfare_annual: Decimal = Field(Decimal("0"), ge=0, max_digits=10, decimal_places=2)
    salary_months: Literal[12, 13, 14] = 12
    manual_net_override: Optional[Decimal] = Field(None, ge=0, max_digits=10, decimal_places=2)


class OnboardingPayload(BaseModel):
    tracking_start_date: str
    main_bank: MainBankIn
    additional_banks: list[AdditionalBankIn] = Field(default_factory=list)
    payment_methods: list[PaymentMethodIn] = Field(default_factory=list)
    saving_accounts: list[SavingAccountIn] = Field(default_factory=list)
    investment_accounts: list[InvestmentAccountIn] = Field(default_factory=list)
    salary: Optional[SalaryIn] = None

    @field_validator("tracking_start_date")
    @classmethod
    def validate_tracking_start_date(cls, value: str) -> str:
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            raise ValueError("Tracking start date must be YYYY-MM-DD")
        try:
            parsed = datetime.date.fromisoformat(value)
        except ValueError:
            raise ValueError("Tracking start date must be YYYY-MM-DD")
        if parsed.day != 1:
            raise ValueError("Tracking start date must be the first day of a month")
        return value

    @model_validator(mode="after")
    def validate_nested_accounts(self) -> OnboardingPayload:
        bank_names = [self.main_bank.name, *(bank.name for bank in self.additional_banks)]
        payment_method_names = [*bank_names, *(method.name for method in self.payment_methods)]

        self._reject_duplicates(payment_method_names, "bank and payment method")
        self._reject_duplicates(
            [account.name for account in self.saving_accounts], "saving account"
        )
        self._reject_duplicates(
            [account.name for account in self.investment_accounts], "investment account"
        )

        banks_by_normalized_name = {name.casefold(): name for name in bank_names}
        for method in self.payment_methods:
            if method.linked_bank_name is None:
                if method.type in BANK_FUNDED_CARD_TYPES:
                    raise ValueError(
                        "Linked bank name is required for bank-funded card payment methods"
                    )
                continue
            bank_name = banks_by_normalized_name.get(method.linked_bank_name.casefold())
            if bank_name is None:
                raise ValueError(
                    f"Linked bank {method.linked_bank_name!r} is not included in onboarding"
                )
            method.linked_bank_name = bank_name
        return self

    @staticmethod
    def _reject_duplicates(names: list[str], label: str) -> None:
        if len({name.casefold() for name in names}) != len(names):
            raise ValueError(f"Duplicate {label} names are not allowed")
