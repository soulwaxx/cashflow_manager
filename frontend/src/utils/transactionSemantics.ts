import type { PaymentMethod, Transaction } from '../types/api';

type TransactionDirection = Transaction['transaction_direction'];

export interface SupportedTransactionCashImpact {
  isSupported: true;
  direction: TransactionDirection;
  label: string;
  displaySign: '+' | '-';
  bankBalanceDelta: -1 | 0 | 1;
  summaryIncomeDelta: -1 | 0 | 1;
  summaryOutcomeDelta: -1 | 0 | 1;
}

export interface UnsupportedTransactionCashImpact {
  isSupported: false;
  label: 'Unsupported';
  bankBalanceDelta: 0;
  summaryIncomeDelta: 0;
  summaryOutcomeDelta: 0;
}

export type TransactionCashImpact = SupportedTransactionCashImpact | UnsupportedTransactionCashImpact;

const PURCHASE: SupportedTransactionCashImpact = {
  isSupported: true,
  direction: 'debit',
  label: 'Purchase',
  displaySign: '-',
  bankBalanceDelta: -1,
  summaryIncomeDelta: 0,
  summaryOutcomeDelta: 1,
};
const REFUND: SupportedTransactionCashImpact = {
  isSupported: true,
  direction: 'credit',
  label: 'Refund',
  displaySign: '+',
  bankBalanceDelta: 1,
  summaryIncomeDelta: 0,
  summaryOutcomeDelta: -1,
};
const INCOME: SupportedTransactionCashImpact = {
  isSupported: true,
  direction: 'income',
  label: 'Income',
  displaySign: '+',
  bankBalanceDelta: 1,
  summaryIncomeDelta: 1,
  summaryOutcomeDelta: 0,
};
const CARD_PAYMENT: SupportedTransactionCashImpact = {
  isSupported: true,
  direction: 'credit',
  label: 'Card payment',
  displaySign: '-',
  bankBalanceDelta: -1,
  summaryIncomeDelta: 0,
  summaryOutcomeDelta: 1,
};
const NON_BANK_PURCHASE: SupportedTransactionCashImpact = { ...PURCHASE, bankBalanceDelta: 0 };
const NON_BANK_INCOME: SupportedTransactionCashImpact = { ...INCOME, bankBalanceDelta: 0 };
const UNSUPPORTED: UnsupportedTransactionCashImpact = {
  isSupported: false,
  label: 'Unsupported',
  bankBalanceDelta: 0,
  summaryIncomeDelta: 0,
  summaryOutcomeDelta: 0,
};

const CASH_IMPACTS_BY_PAYMENT_METHOD: Record<
  PaymentMethod['type'],
  Partial<Record<TransactionDirection, SupportedTransactionCashImpact>>
> = {
  bank: { debit: PURCHASE, income: INCOME },
  debit_card: { debit: PURCHASE, credit: REFUND },
  credit_card: { debit: PURCHASE, credit: CARD_PAYMENT },
  revolving: { debit: PURCHASE, credit: CARD_PAYMENT },
  prepaid: { debit: NON_BANK_PURCHASE, income: NON_BANK_INCOME },
  cash: { debit: NON_BANK_PURCHASE, income: NON_BANK_INCOME },
};

export function directionsForPaymentMethod(type: PaymentMethod['type'] | undefined): SupportedTransactionCashImpact[] {
  if (!type) return [];
  return Object.values(CASH_IMPACTS_BY_PAYMENT_METHOD[type]).filter(
    (impact): impact is SupportedTransactionCashImpact => impact !== undefined,
  );
}

export function cashImpactForTransaction(
  type: PaymentMethod['type'] | undefined,
  direction: TransactionDirection,
): TransactionCashImpact {
  return (type && CASH_IMPACTS_BY_PAYMENT_METHOD[type][direction]) ?? UNSUPPORTED;
}
