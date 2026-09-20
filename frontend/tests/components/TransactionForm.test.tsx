import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';
import TransactionForm from '../../src/components/transactions/TransactionForm';

const methods = [
  { id: 'bank', name: 'Bank', type: 'bank', is_main_bank: true, linked_bank_id: null, opening_balance: null, is_active: true },
  { id: 'debit', name: 'Debit card', type: 'debit_card', is_main_bank: false, linked_bank_id: 'bank', opening_balance: null, is_active: true },
  { id: 'credit', name: 'Credit card', type: 'credit_card', is_main_bank: false, linked_bank_id: 'bank', opening_balance: null, is_active: true },
];

function wrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

test('TransactionForm uses refund and card-payment terms from the direction matrix', async () => {
  server.use(
    http.get('/api/v1/payment-methods', () => HttpResponse.json(methods)),
    http.get('/api/v1/categories', () => HttpResponse.json([])),
  );
  const user = userEvent.setup();
  render(<TransactionForm onSuccess={() => {}} />, { wrapper });

  const paymentMethod = await screen.findByLabelText(/payment method/i);
  await screen.findByRole('option', { name: 'Debit card (debit_card)' });
  await user.selectOptions(paymentMethod, 'debit');
  expect(screen.getByRole('option', { name: 'Refund' })).toBeInTheDocument();
  expect(screen.queryByRole('option', { name: 'Card payment' })).not.toBeInTheDocument();

  await user.selectOptions(paymentMethod, 'credit');
  expect(screen.getByRole('option', { name: 'Card payment' })).toBeInTheDocument();
  expect(screen.queryByRole('option', { name: 'Refund' })).not.toBeInTheDocument();
});
