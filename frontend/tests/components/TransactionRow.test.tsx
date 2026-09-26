import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
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
  const { container } = render(
    <TransactionRow
      tx={{ ...transaction, transaction_direction: transactionDirection }}
      method={paymentMethod(type)}
      onEdit={() => {}}
      onDelete={() => {}}
    />,
  );

  expect(screen.getByText(expectedBadge)).toBeInTheDocument();
  const desktopActions = container.querySelector('.hidden.sm\\:flex');
  expect(desktopActions).toBeInTheDocument();
  expect(within(desktopActions as HTMLElement).getByRole('button', { name: 'Edit Transaction' })).toBeInTheDocument();
  expect(within(desktopActions as HTMLElement).getByRole('button', { name: 'Delete Transaction' })).toBeInTheDocument();
});

test('mobile edit and delete actions are disclosed accessibly and preserve callbacks', async () => {
  const user = userEvent.setup();
  const onEdit = vi.fn();
  const onDelete = vi.fn();
  const { container } = render(
    <TransactionRow tx={transaction} method={paymentMethod('bank')} onEdit={onEdit} onDelete={onDelete} />,
  );
  const details = screen.getByText('Details').closest('details')!;
  expect(within(details).getByText('Details')).toHaveClass('min-h-11', 'min-w-[5.5rem]');
  expect(details).not.toHaveAttribute('open');
  await user.click(within(details).getByText('Details'));
  await user.click(within(details).getByRole('button', { name: 'Edit Transaction' }));
  await user.click(within(details).getByRole('button', { name: 'Delete Transaction' }));
  expect(onEdit).toHaveBeenCalledOnce();
  expect(onDelete).toHaveBeenCalledOnce();

  const desktopActions = container.querySelector('.hidden.sm\\:flex');
  expect(desktopActions).toBeInTheDocument();
  expect(within(desktopActions as HTMLElement).getByRole('button', { name: 'Edit Transaction' })).toBeInTheDocument();
  expect(within(desktopActions as HTMLElement).getByRole('button', { name: 'Delete Transaction' })).toBeInTheDocument();
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
