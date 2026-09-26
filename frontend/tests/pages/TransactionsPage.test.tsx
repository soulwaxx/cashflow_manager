import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';
import { AuthProvider } from '../../src/contexts/AuthContext';
import TransactionsPage from '../../src/pages/TransactionsPage';

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <AuthProvider>{children}</AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

const mockTransactions = [
  {
    id: 'tx1', user_id: 'u1', date: '2026-03-15', detail: 'Grocery run',
    amount: 45.50, payment_method_id: 'pm1', category_id: 'cat1',
    transaction_direction: 'debit', billing_month: '2026-03-01',
    recurrence_months: null,
    parent_transaction_id: null, notes: null, created_at: '', updated_at: '',
  },
  {
    id: 'tx2', user_id: 'u1', date: '2026-03-01', detail: 'Salary',
    amount: 2800, payment_method_id: 'pm2', category_id: 'cat2',
    transaction_direction: 'income', billing_month: '2026-03-01',
    recurrence_months: 12,
    parent_transaction_id: null, notes: null, created_at: '', updated_at: '',
  },
];

beforeEach(() => {
  server.use(
    http.get('/api/v1/transactions', () => HttpResponse.json(mockTransactions)),
    http.get('/api/v1/payment-methods', () =>
      HttpResponse.json([
        { id: 'pm1', name: 'Visa', type: 'credit_card', is_main_bank: false, is_active: true },
        { id: 'pm2', name: 'Salary bank', type: 'bank', is_main_bank: true, is_active: true },
      ])
    ),
    http.get('/api/v1/categories', () =>
      HttpResponse.json([
        { id: 'cat1', type: 'Personal', sub_type: 'Food', is_active: true },
        { id: 'cat2', type: 'Income', sub_type: 'Salary', is_active: true },
      ])
    ),
  );
});

test('TransactionsPage lists transactions', async () => {
  render(<TransactionsPage />, { wrapper });
  await waitFor(() => expect(screen.getByText('Grocery run')).toBeInTheDocument());
  expect(screen.getByText('Salary')).toBeInTheDocument();
});

test('TransactionsPage shows recurring indicator for recurrence_months set', async () => {
  render(<TransactionsPage />, { wrapper });
  await waitFor(() => expect(screen.getByText('Salary')).toBeInTheDocument());
  expect(screen.getByTitle(/recurring/i)).toBeInTheDocument();
});

test('TransactionsPage opens add form when button clicked', async () => {
  const user = userEvent.setup();
  render(<TransactionsPage />, { wrapper });
  await waitFor(() => expect(screen.getByRole('button', { name: /add transaction/i })).toBeInTheDocument());
  await user.click(screen.getByRole('button', { name: /add transaction/i }));
  expect(screen.getByRole('dialog')).toBeInTheDocument();
});

test('Dashboard shortcut query opens the existing add form', async () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/transactions?add=1']}>
        <AuthProvider><TransactionsPage /></AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
  expect(await screen.findByRole('dialog', { name: /add transaction/i })).toBeInTheDocument();
  expect(screen.getByLabelText(/payment method/i)).toBeInTheDocument();
});

test('TransactionsPage renders transaction list with amounts and details', async () => {
  render(<TransactionsPage />, { wrapper });
  await waitFor(() => expect(screen.getByText('Grocery run')).toBeInTheDocument());
  // Amount formatted as Italian locale: 45.50 → "45,50"
  expect(screen.getByText(/45,50/)).toBeInTheDocument();
  expect(screen.getByText('Salary')).toBeInTheDocument();
  // Amount for salary: 2800 → "2.800,00"
  expect(screen.getByText(/2\.800/)).toBeInTheDocument();
});

test('TransactionsPage delete button opens cascade modal', async () => {
  const user = userEvent.setup();
  render(<TransactionsPage />, { wrapper });
  await waitFor(() => expect(screen.getByText('Grocery run')).toBeInTheDocument());

  // Each transaction row has a Delete button; click the first one (Grocery run, non-recurring)
  const deleteButtons = screen.getAllByRole('button', { name: /delete/i });
  await user.click(deleteButtons[0]);

  // CascadeDeleteModal opens as a dialog with title "Delete transaction"
  expect(screen.getByRole('dialog')).toBeInTheDocument();
  expect(screen.getByText(/delete transaction/i)).toBeInTheDocument();
  // Non-recurring: shows the simple confirmation message
  expect(screen.getByText(/delete this transaction\?/i)).toBeInTheDocument();
});

test('TransactionsPage delete button opens cascade modal with recurring options for recurring transaction', async () => {
  const user = userEvent.setup();
  render(<TransactionsPage />, { wrapper });
  await waitFor(() => expect(screen.getByText('Salary')).toBeInTheDocument());

  // Salary transaction is recurring (recurrence_months: 12)
  // It appears second in the list; find all Delete buttons and click the one for Salary
  const salaryRow = screen.getByText('Salary').closest('li')!;
  const desktopActions = salaryRow.querySelector<HTMLElement>('.hidden.sm\\:flex')!;
  const deleteBtn = within(desktopActions).getByRole('button', { name: /delete/i });
  await user.click(deleteBtn);

  expect(screen.getByRole('dialog')).toBeInTheDocument();
  // Recurring variant shows cascade options
  expect(screen.getByText(/recurring transaction/i)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /this one only/i })).toBeInTheDocument();
});

test('TransactionsPage date controls are labeled and have 44px targets', async () => {
  render(<TransactionsPage />, { wrapper });
  await waitFor(() => expect(screen.getByText('Grocery run')).toBeInTheDocument());
  expect(screen.getByLabelText('Transaction year')).toHaveClass('min-h-11');
  expect(screen.getByLabelText('Transaction month')).toHaveClass('min-h-11');
  expect(screen.getByRole('button', { name: /by date/i })).toHaveClass('min-h-11');
  expect(screen.getByRole('button', { name: /by billing month/i })).toHaveClass('min-h-11');
});

test('TransactionsPage defaults to billing mode when billing_month URL param is present', async () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/transactions?billing_month=2026-05-01']}>
        <AuthProvider><TransactionsPage /></AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
  await waitFor(() => expect(screen.getByText('Grocery run')).toBeInTheDocument());
  const billingBtn = screen.getByRole('button', { name: /by billing month/i });
  expect(billingBtn.className).toContain('bg-blue-600');
  const dateBtn = screen.getByRole('button', { name: /by date/i });
  expect(dateBtn.className).not.toContain('bg-blue-600');
});

test('TransactionRow shows billing annotation when billing_month differs from date month', async () => {
  server.use(
    http.get('/api/v1/transactions', () =>
      HttpResponse.json([{
        id: 'tx-cc', user_id: 'u1', date: '2026-01-15', detail: 'CC Dinner',
        amount: 80, payment_method_id: 'pm1', category_id: null,
        transaction_direction: 'debit', billing_month: '2026-02-01',
        recurrence_months: null,
        parent_transaction_id: null, notes: null, created_at: '', updated_at: '',
      }])
    )
  );
  render(<TransactionsPage />, { wrapper });
  await waitFor(() => expect(screen.getByText('CC Dinner')).toBeInTheDocument());
  expect(screen.getByText(/billed 2026-02/)).toBeInTheDocument();
});

test('TransactionForm shows billing hint for credit_card payment method', async () => {
  const user = userEvent.setup();
  render(<TransactionsPage />, { wrapper });
  await waitFor(() => screen.getByRole('button', { name: /add transaction/i }));
  await user.click(screen.getByRole('button', { name: /add transaction/i }));
  // Select credit_card method
  const methodSelect = screen.getByLabelText(/payment method/i);
  await user.selectOptions(methodSelect, 'pm1');
  expect(screen.getByText(/billed in/i)).toBeInTheDocument();
});

test('Transaction edit form only exposes backend-supported fields', async () => {
  const user = userEvent.setup();
  let requestBody: unknown;

  server.use(
    http.put('/api/v1/transactions/tx2', async ({ request }) => {
      requestBody = await request.json();
      return HttpResponse.json({
        ...mockTransactions[1],
        detail: 'Updated salary',
      });
    })
  );

  render(<TransactionsPage />, { wrapper });
  await waitFor(() => expect(screen.getByText('Salary')).toBeInTheDocument());

  const salaryRow = screen.getByText('Salary').closest('li')!;
  const desktopActions = salaryRow.querySelector<HTMLElement>('.hidden.sm\\:flex')!;
  await user.click(within(desktopActions).getByRole('button', { name: /edit/i }));

  await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());
  expect(screen.queryByLabelText(/payment method/i)).not.toBeInTheDocument();
  expect(screen.queryByLabelText(/^direction$/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/recurring every/i)).not.toBeInTheDocument();
  expect(screen.getByLabelText(/apply changes to/i)).toBeInTheDocument();

  await user.click(screen.getByRole('button', { name: /save changes/i }));

  await waitFor(() => expect(requestBody).toBeTruthy());
  expect(requestBody).toMatchObject({
    date: '2026-03-01',
    detail: 'Salary',
    amount: 2800,
    category_id: 'cat2',
  });
  expect(requestBody).not.toHaveProperty('payment_method_id');
  expect(requestBody).not.toHaveProperty('transaction_direction');
  expect(requestBody).not.toHaveProperty('recurrence_months');
});

test('Transaction edit form sends null when notes are cleared', async () => {
  const user = userEvent.setup();
  let requestBody: unknown;
  const txWithNote = { ...mockTransactions[0], notes: 'old note' };

  server.use(
    http.get('/api/v1/transactions', () => HttpResponse.json([txWithNote])),
    http.put('/api/v1/transactions/tx1', async ({ request }) => {
      requestBody = await request.json();
      return HttpResponse.json({ ...txWithNote, notes: null });
    })
  );

  render(<TransactionsPage />, { wrapper });
  await waitFor(() => expect(screen.getByText('Grocery run')).toBeInTheDocument());

  const row = screen.getByText('Grocery run').closest('li')!;
  const desktopActions = row.querySelector<HTMLElement>('.hidden.sm\\:flex')!;
  await user.click(within(desktopActions).getByRole('button', { name: /edit/i }));

  const notesInput = screen.getByLabelText(/notes/i);
  await user.clear(notesInput);
  await user.click(screen.getByRole('button', { name: /save changes/i }));

  await waitFor(() => expect(requestBody).toBeTruthy());
  expect(requestBody).toMatchObject({ notes: null });
});
