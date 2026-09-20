import { render, screen } from '@testing-library/react';
import TransactionRow from '../../src/components/transactions/TransactionRow';
import type { PaymentMethod, Transaction } from '../../src/types/api';

const transaction: Transaction = {
  id: 'tx-1',
  user_id: 'user-1',
  date: '2026-01-15',
  detail: 'Transaction',
  amount: 25,
  payment_method_id: 'method-1',
  category_id: null,
  transaction_direction: 'debit',
  billing_month: '2026-01-01',
  recurrence_months: null,
  parent_transaction_id: null,
  notes: null,
  created_at: '',
  updated_at: '',
};

function paymentMethod(type: PaymentMethod['type']): PaymentMethod {
  return {
    id: 'method-1',
    user_id: 'user-1',
    name: 'Method',
    type,
    is_main_bank: type === 'bank',
    linked_bank_id: null,
    opening_balance: null,
    is_active: true,
  };
}

test.each([
  ['debit-card refund', 'debit_card', 'credit', 'Refund +€25,00'],
  ['card payment', 'credit_card', 'credit', 'Card payment -€25,00'],
  ['purchase', 'bank', 'debit', 'Purchase -€25,00'],
  ['income', 'bank', 'income', 'Income +€25,00'],
] as const)('%s row uses the summary and bank-balance cash-impact sign', (
  _description,
  type,
  transactionDirection,
  expectedBadge,
) => {
  render(
    <TransactionRow
      tx={{ ...transaction, transaction_direction: transactionDirection }}
      method={paymentMethod(type)}
      onEdit={() => {}}
      onDelete={() => {}}
    />,
  );

  expect(screen.getByText(expectedBadge)).toBeInTheDocument();
});

test.each([
  ['bank credit', 'bank', 'credit'],
  ['debit-card income', 'debit_card', 'income'],
  ['credit-card income', 'credit_card', 'income'],
  ['revolving income', 'revolving', 'income'],
  ['prepaid credit', 'prepaid', 'credit'],
  ['cash credit', 'cash', 'credit'],
] as const)('%s legacy row is marked unsupported without a fabricated sign', (
  _description,
  type,
  transactionDirection,
) => {
  render(
    <TransactionRow
      tx={{ ...transaction, transaction_direction: transactionDirection }}
      method={paymentMethod(type)}
      onEdit={() => {}}
      onDelete={() => {}}
    />,
  );

  expect(screen.getByText('Unsupported · €25,00 (no cash impact)')).toBeInTheDocument();
  expect(screen.queryByText(/Unsupported [+-]€/)).not.toBeInTheDocument();
});
