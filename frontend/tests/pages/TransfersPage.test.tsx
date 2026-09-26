import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';
import { AuthProvider } from '../../src/contexts/AuthContext';
import TransfersPage from '../../src/pages/TransfersPage';

const PAGE_SIZE = 100;

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}><MemoryRouter><AuthProvider>{children}</AuthProvider></MemoryRouter></QueryClientProvider>
  );
}

const mockTransfers = [
  {
    id: 'tr1', user_id: 'u1', date: '2026-01-15', detail: 'Savings deposit',
    amount: 500, from_account_type: 'bank', from_account_name: 'Checking',
    to_account_type: 'saving', to_account_name: 'Savings',
    billing_month: '2026-01-01', recurrence_months: null, notes: null,
    parent_transfer_id: null, created_at: '',
  },
  {
    id: 'tr2', user_id: 'u1', date: '2026-02-10', detail: 'Emergency fund',
    amount: 200, from_account_type: 'bank', from_account_name: 'Checking',
    to_account_type: 'saving', to_account_name: 'Savings',
    billing_month: '2026-02-01', recurrence_months: null, notes: null,
    parent_transfer_id: null, created_at: '',
  },
];

beforeEach(() => {
  server.use(
    http.get('/api/v1/transfers', () => HttpResponse.json(mockTransfers)),
    http.get('/api/v1/payment-methods', () =>
      HttpResponse.json([
        { id: 'pm1', name: 'Checking', type: 'bank', is_active: true, is_main_bank: true },
        { id: 'pm2', name: 'Savings', type: 'bank', is_active: true, is_main_bank: false },
      ])
    ),
  );
});

test('TransfersPage renders heading', async () => {
  render(<TransfersPage />, { wrapper });
  await waitFor(() => expect(screen.getByText('Transfers')).toBeInTheDocument());
});

test('TransfersPage shows transfer list', async () => {
  render(<TransfersPage />, { wrapper });
  await waitFor(() => expect(screen.getByText('Savings deposit')).toBeInTheDocument());
  expect(screen.getByText('Emergency fund')).toBeInTheDocument();
});

test('TransfersPage lists transfers with from/to accounts', async () => {
  render(<TransfersPage />, { wrapper });
  await waitFor(() => expect(screen.getByText('Savings deposit')).toBeInTheDocument());
  expect(screen.getAllByText(/Checking/).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/Savings/).length).toBeGreaterThan(0);
  const transferRow = screen.getByText('Savings deposit').closest('li')!;
  expect(within(transferRow).getByText('From')).toHaveClass('sr-only');
  expect(within(transferRow).getByText('to')).toHaveClass('sr-only');
  expect(transferRow).toHaveTextContent(/From Checking → to Savings/);
});

test('TransfersPage delete button opens modal', async () => {
  const user = userEvent.setup();
  render(<TransfersPage />, { wrapper });
  await waitFor(() => expect(screen.getByText('Savings deposit')).toBeInTheDocument());
  const deleteButtons = screen.getAllByRole('button', { name: /delete/i });
  await user.click(deleteButtons[0]);
  expect(screen.getByRole('dialog')).toBeInTheDocument();
  expect(screen.getByText(/delete this transfer\?/i)).toBeInTheDocument();
});

test('TransfersPage opens add form', async () => {
  const user = userEvent.setup();
  render(<TransfersPage />, { wrapper });
  await waitFor(() => screen.getByRole('button', { name: /add transfer/i }));
  await user.click(screen.getByRole('button', { name: /add transfer/i }));
  expect(screen.getByRole('dialog')).toBeInTheDocument();
});

test('Transfer creation submits stable account IDs', async () => {
  const user = userEvent.setup();
  let requestBody: unknown;
  server.use(
    http.get('/api/v1/accounts', () => HttpResponse.json([
      { id: 'saving-1', user_id: 'u1', type: 'saving', name: 'Savings', opening_balance: 1000, is_active: true },
    ])),
    http.post('/api/v1/transfers', async ({ request }) => {
      requestBody = await request.json();
      return HttpResponse.json(mockTransfers[0]);
    })
  );

  render(<TransfersPage />, { wrapper });
  await user.click(await screen.findByRole('button', { name: /add transfer/i }));
  await user.type(screen.getByLabelText(/^detail/i), 'Stable transfer');
  await user.type(screen.getByLabelText(/^amount/i), '100');
  await waitFor(() => expect(screen.getAllByRole('combobox')).toHaveLength(4));
  const selects = screen.getAllByRole('combobox');
  await user.selectOptions(selects[1], 'pm1');
  await user.selectOptions(selects[3], 'saving-1');
  await user.click(screen.getByRole('button', { name: /^add transfer$/i }));

  await waitFor(() => expect(requestBody).toEqual(expect.objectContaining({
    from_account_type: 'bank', from_account_id: 'pm1',
    to_account_type: 'saving', to_account_id: 'saving-1',
  })));
  expect(requestBody).not.toHaveProperty('from_account_name');
  expect(requestBody).not.toHaveProperty('to_account_name');
});


test('Transfer edit form only exposes backend-supported fields', async () => {
  const user = userEvent.setup();
  let requestBody: unknown;

  server.use(
    http.put('/api/v1/transfers/tr1', async ({ request }) => {
      requestBody = await request.json();
      return HttpResponse.json({
        ...mockTransfers[0],
        detail: 'Updated savings deposit',
      });
    })
  );

  render(<TransfersPage />, { wrapper });
  await waitFor(() => expect(screen.getByText('Savings deposit')).toBeInTheDocument());

  const transferRow = screen.getByText('Savings deposit').closest('li')!;
  await user.click(within(transferRow).getByRole('button', { name: /edit/i }));

  await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());
  expect(screen.queryByLabelText(/from account type/i)).not.toBeInTheDocument();
  expect(screen.queryByLabelText(/from account name/i)).not.toBeInTheDocument();
  expect(screen.queryByLabelText(/to account type/i)).not.toBeInTheDocument();
  expect(screen.queryByLabelText(/to account name/i)).not.toBeInTheDocument();
  expect(screen.queryByLabelText(/repeat for n months/i)).not.toBeInTheDocument();
  expect(screen.getByLabelText(/notes/i)).toBeInTheDocument();

  await user.type(screen.getByLabelText(/notes/i), 'updated note');
  await user.click(screen.getByRole('button', { name: /save changes/i }));

  await waitFor(() => expect(requestBody).toBeTruthy());
  expect(requestBody).toMatchObject({
    date: '2026-01-15',
    detail: 'Savings deposit',
    amount: 500,
    notes: 'updated note',
  });
  expect(requestBody).not.toHaveProperty('from_account_type');
  expect(requestBody).not.toHaveProperty('from_account_name');
  expect(requestBody).not.toHaveProperty('to_account_type');
  expect(requestBody).not.toHaveProperty('to_account_name');
  expect(requestBody).not.toHaveProperty('recurrence_months');
});


test('Transfer edit updates amount value', async () => {
  const user = userEvent.setup();
  let requestBody: unknown = null;

  server.use(
    http.put('/api/v1/transfers/tr1', async ({ request }) => {
      requestBody = await request.json();
      return HttpResponse.json({
        ...mockTransfers[0],
        amount: 650,
      });
    })
  );

  render(<TransfersPage />, { wrapper });
  await waitFor(() => expect(screen.getByText('Savings deposit')).toBeInTheDocument());

  const transferRow = screen.getByText('Savings deposit').closest('li')!;
  await user.click(within(transferRow).getByRole('button', { name: /edit/i }));

  const amountInput = screen.getByLabelText(/amount/i);
  await user.clear(amountInput);
  await user.type(amountInput, '650');
  await user.click(screen.getByRole('button', { name: /save changes/i }));

  await waitFor(() => expect(requestBody).toBeTruthy());
  expect(requestBody).toMatchObject({
    amount: 650,
  });
});

test('Transfer edit form sends null when notes are cleared', async () => {
  const user = userEvent.setup();
  let requestBody: unknown = null;
  const transferWithNote = { ...mockTransfers[0], notes: 'old note' };

  server.use(
    http.get('/api/v1/transfers', () => HttpResponse.json([transferWithNote])),
    http.put('/api/v1/transfers/tr1', async ({ request }) => {
      requestBody = await request.json();
      return HttpResponse.json({ ...transferWithNote, notes: null });
    })
  );

  render(<TransfersPage />, { wrapper });
  await waitFor(() => expect(screen.getByText('Savings deposit')).toBeInTheDocument());

  const transferRow = screen.getByText('Savings deposit').closest('li')!;
  await user.click(within(transferRow).getByRole('button', { name: /edit/i }));

  const notesInput = screen.getByLabelText(/notes/i);
  await user.clear(notesInput);
  await user.click(screen.getByRole('button', { name: /save changes/i }));

  await waitFor(() => expect(requestBody).toBeTruthy());
  expect(requestBody).toMatchObject({ notes: null });
});

test('TransfersPage loads additional transfer pages on demand', async () => {
  const firstPage = Array.from({ length: PAGE_SIZE }, (_, i) => ({
    id: `tr-${i}`,
    user_id: 'u1',
    date: '2026-01-15',
    detail: `Transfer ${i}`,
    amount: 10,
    from_account_type: 'bank',
    from_account_name: 'Checking',
    to_account_type: 'saving',
    to_account_name: 'Savings',
    billing_month: '2026-01-01',
    recurrence_months: null,
    notes: null,
    parent_transfer_id: null,
    created_at: '',
  }));
  const secondPage = [
    {
      id: 'tr-last',
      user_id: 'u1',
      date: '2026-02-15',
      detail: 'Last transfer',
      amount: 25,
      from_account_type: 'bank',
      from_account_name: 'Checking',
      to_account_type: 'saving',
      to_account_name: 'Savings',
      billing_month: '2026-02-01',
      recurrence_months: null,
      notes: null,
      parent_transfer_id: null,
      created_at: '',
    },
  ];

  server.use(
    http.get('/api/v1/transfers', ({ request }) => {
      const url = new URL(request.url);
      const limit = Number(url.searchParams.get('limit'));
      const offset = Number(url.searchParams.get('offset'));
      if (limit !== PAGE_SIZE) {
        return HttpResponse.json({ detail: 'unexpected limit' }, { status: 500 });
      }
      if (offset === 0) return HttpResponse.json(firstPage);
      if (offset === PAGE_SIZE) return HttpResponse.json(secondPage);
      return HttpResponse.json([]);
    })
  );

  const user = userEvent.setup();
  render(<TransfersPage />, { wrapper });

  await waitFor(() => expect(screen.getByText('Transfer 0')).toBeInTheDocument());
  expect(screen.queryByText('Last transfer')).not.toBeInTheDocument();

  await user.click(screen.getByRole('button', { name: /load more/i }));

  await waitFor(() => expect(screen.getByText('Last transfer')).toBeInTheDocument());
});
