from datetime import date
from dateutil.relativedelta import relativedelta

CURRENT_MONTH_TYPES = {"bank", "debit_card", "prepaid", "cash"}
NEXT_MONTH_TYPES = {"credit_card", "revolving"}
BANK_FUNDED_CARD_TYPES = NEXT_MONTH_TYPES | {"debit_card"}


def billing_month(payment_method_type: str, transaction_date: date) -> date:
    if payment_method_type in CURRENT_MONTH_TYPES:
        return transaction_date.replace(day=1)
    if payment_method_type in NEXT_MONTH_TYPES:
        return (transaction_date.replace(day=1) + relativedelta(months=1))
    raise ValueError(f"Unknown payment method type: {payment_method_type!r}")
