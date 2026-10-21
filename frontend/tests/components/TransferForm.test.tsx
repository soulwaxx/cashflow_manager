import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';
import TransferForm from '../../src/components/transfers/TransferForm';
import type { Transfer } from '../../src/types/api';

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const accounts = [
  { id: 'fund-1', user_id: 'u1', type: 'pension', name: 'Work fund', opening_balance: 0, opening_balance_month: '2026-01-01', is_active: true },
  { id: 'save-1', user_id: 'u1', type: 'saving', name: 'Savings', opening_balance: 0, is_active: true },
];

function transfer(fromType: Transfer['from_account_type'], toType: Transfer['to_account_type']): Transfer {
  const pensionFrom = fromType === 'pension';
  const pensionTo = toType === 'pension';
  return {
    id: 'transfer-1', user_id: 'u1', date: '2026-01-10', detail: 'Fund movement', amount: 25,
    from_account_type: fromType, from_account_id: pensionFrom ? 'fund-1' : 'save-1', from_payment_method_id: null, from_account_name: pensionFrom ? 'Work fund' : 'Savings',
    to_account_type: toType, to_account_id: pensionTo ? 'fund-1' : 'save-1', to_payment_method_id: null, to_account_name: pensionTo ? 'Work fund' : 'Savings',
    billing_month: '2026-01-01', recurrence_months: null, parent_transfer_id: null, notes: null, created_at: '2026-01-10',
  };
}

beforeEach(() => server.use(
  http.get('/api/v1/accounts', () => HttpResponse.json(accounts)),
  http.get('/api/v1/payment-methods', () => HttpResponse.json([])),
));

function expectPensionGuidance() {
  expect(screen.getByRole('note')).toHaveTextContent(/configured payroll credits are already projected/i);
  expect(screen.getByRole('note')).toHaveTextContent(/transfers are additional movements/i);
  expect(screen.getByRole('note')).toHaveTextContent(/reconcile.*dated balance/i);
}

test('shows pension guidance and submits a transfer to pension', async () => {
  const user = userEvent.setup();
  let submitted = false;
  server.use(http.post('/api/v1/transfers', () => { submitted = true; return HttpResponse.json({ id: 't1' }); }));
  render(<TransferForm onSuccess={() => undefined} />, { wrapper });
  await user.selectOptions(await screen.findByLabelText('To account type'), 'pension');
  await user.selectOptions(document.querySelector('select[name="to_account_id"]')!, 'fund-1');
  await user.selectOptions(screen.getByLabelText('From account type'), 'saving');
  await user.selectOptions(document.querySelector('select[name="from_account_id"]')!, 'save-1');
  expectPensionGuidance();
  await user.type(screen.getByLabelText(/Detail/i), 'Additional transfer');
  await user.type(screen.getByLabelText(/Amount/i), '10');
  await user.click(screen.getByRole('button', { name: 'Add transfer' }));
  await waitFor(() => expect(submitted).toBe(true));
});

test('shows pension guidance and submits a transfer from pension', async () => {
  const user = userEvent.setup();
  let submitted = false;
  server.use(http.post('/api/v1/transfers', () => { submitted = true; return HttpResponse.json({ id: 't2' }); }));
  render(<TransferForm onSuccess={() => undefined} />, { wrapper });
  await user.selectOptions(await screen.findByLabelText('From account type'), 'pension');
  await user.selectOptions(document.querySelector('select[name="from_account_id"]')!, 'fund-1');
  await user.selectOptions(screen.getByLabelText('To account type'), 'saving');
  await user.selectOptions(document.querySelector('select[name="to_account_id"]')!, 'save-1');
  expectPensionGuidance();
  await user.type(screen.getByLabelText(/Detail/i), 'Additional transfer out');
  await user.type(screen.getByLabelText(/Amount/i), '10');
  await user.click(screen.getByRole('button', { name: 'Add transfer' }));
  await waitFor(() => expect(submitted).toBe(true));
});

test('shows pension guidance when editing a transfer to pension', async () => {
  render(<TransferForm initial={transfer('saving', 'pension')} onSuccess={() => undefined} />, { wrapper });
  expectPensionGuidance();
});

test('shows pension guidance when editing a transfer from pension', async () => {
  render(<TransferForm initial={transfer('pension', 'saving')} onSuccess={() => undefined} />, { wrapper });
  expectPensionGuidance();
});

test('does not show pension guidance when creating a non-pension transfer', async () => {
  const user = userEvent.setup();
  render(<TransferForm onSuccess={() => undefined} />, { wrapper });
  await user.selectOptions(await screen.findByLabelText('To account type'), 'saving');
  expect(screen.queryByRole('note')).not.toBeInTheDocument();
});

test('does not show pension guidance when editing a non-pension transfer', async () => {
  render(<TransferForm initial={transfer('saving', 'saving')} onSuccess={() => undefined} />, { wrapper });
  expect(await screen.findByLabelText(/Detail/i)).toBeInTheDocument();
  expect(screen.queryByRole('note')).not.toBeInTheDocument();
});
