"""Shared transaction direction and cash-impact semantics.

The transaction direction is interpreted with its payment-method type.  This
matrix is the backend source of truth for API validation, main-bank balances,
and monthly summary aggregates.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class TransactionSemantics:
    """Effects per €1 of a valid transaction direction.

    ``bank_balance_delta`` affects the linked effective main bank.  Summary
    deltas are reported as positive income and signed net outcomes; a refund
    therefore reduces outcomes.
    """

    bank_balance_delta: int = 0
    income_delta: int = 0
    outcome_delta: int = 0


_PURCHASE = TransactionSemantics(bank_balance_delta=-1, outcome_delta=1)
_REFUND = TransactionSemantics(bank_balance_delta=1, outcome_delta=-1)
_INCOME = TransactionSemantics(bank_balance_delta=1, income_delta=1)
_NON_BANK_PURCHASE = TransactionSemantics(outcome_delta=1)
_NON_BANK_INCOME = TransactionSemantics(income_delta=1)
_CARD_PAYMENT = TransactionSemantics(bank_balance_delta=-1, outcome_delta=1)


TRANSACTION_SEMANTICS_BY_PM_TYPE: dict[str, dict[str, TransactionSemantics]] = {
    "bank": {
        "income": _INCOME,
        "debit": _PURCHASE,
    },
    "debit_card": {
        "debit": _PURCHASE,
        "credit": _REFUND,
    },
    "credit_card": {
        "debit": _PURCHASE,
        "credit": _CARD_PAYMENT,
    },
    "revolving": {
        "debit": _PURCHASE,
        "credit": _CARD_PAYMENT,
    },
    "prepaid": {
        "income": _NON_BANK_INCOME,
        "debit": _NON_BANK_PURCHASE,
    },
    "cash": {
        "income": _NON_BANK_INCOME,
        "debit": _NON_BANK_PURCHASE,
    },
}


def directions_for_payment_method(payment_method_type: str) -> set[str]:
    return set(TRANSACTION_SEMANTICS_BY_PM_TYPE.get(payment_method_type, {}))


def transaction_semantics(
    payment_method_type: str, transaction_direction: str
) -> TransactionSemantics | None:
    return TRANSACTION_SEMANTICS_BY_PM_TYPE.get(payment_method_type, {}).get(transaction_direction)
