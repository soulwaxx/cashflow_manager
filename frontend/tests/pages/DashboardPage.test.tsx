import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';
import { AuthProvider } from '../../src/contexts/AuthContext';
import DashboardPage from '../../src/pages/DashboardPage';

let assetAsOf: string | null;
const statementMonth = '2026-03-01';

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}><MemoryRouter><AuthProvider>{children}</AuthProvider></MemoryRouter></QueryClientProvider>;
}

function monthIndex(value: string): number {
  const [year, month] = value.slice(0, 7).split('-').map(Number);
  return year * 12 + month;
}

// Navigate to explicit reporting months instead of freezing Date; user-event and query timers stay real.
async function navigateDashboardTo(user: ReturnType<typeof userEvent.setup>, targetMonth: string) {
  const now = new Date();
  const currentMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-01`;
  const difference = monthIndex(targetMonth) - monthIndex(currentMonth);
  const button = difference < 0 ? 'Previous month' : 'Next month';
  for (let step = 0; step < Math.abs(difference); step += 1) {
    await user.click(screen.getByRole('button', { name: button }));
  }
}

function pensionAsset(asOf: string) {
  const reconciled = asOf >= statementMonth;
  const flows = reconciled ? monthIndex(asOf) - monthIndex(statementMonth) : 0;
  const balance = reconciled ? 20_000 + flows * 275 : 10_000 + (monthIndex(asOf) - monthIndex('2025-01-01') + 1) * 275;
  const employee = reconciled ? flows * 25 : (monthIndex(asOf) - monthIndex('2025-01-01') + 1) * 25;
  const employer = reconciled ? flows * 50 : (monthIndex(asOf) - monthIndex('2025-01-01') + 1) * 50;
  const tfr = reconciled ? flows * 200 : (monthIndex(asOf) - monthIndex('2025-01-01') + 1) * 200;
  return {
    asset_type: 'pension', asset_name: 'Renamed fund', account_id: 'stable-fund-id',
    computed_amount: balance, manual_override: null, final_amount: balance,
    valuation_status: reconciled ? 'statement_reconciled' : 'estimated',
    reconciled_as_of_month: reconciled ? statementMonth : null,
    reconciled_balance: reconciled ? 20_000 : null,
    reconciliation_source: reconciled ? 'statement' : null,
    employee_contributions: employee, employer_contributions: employer, tfr_contributions: tfr,
    net_transfers: 0, projected_through: asOf,
  };
}

beforeEach(() => {
  assetAsOf = null;
  const year = new Date().getFullYear();
  const month = new Date().getMonth() + 1;
  server.use(
    http.get(`/api/v1/summary/${year}`, () => HttpResponse.json([
      { year, month, incomes: 3000, outcomes_by_method: {}, transfers_out_bank: 0, transfers_in_bank: 0, bank_balance: 4500 },
    ])),
    http.get(`/api/v1/summary/${year}/${month}`, () => HttpResponse.json({
      year, month, incomes: 3000, outcomes_by_method: { Visa: 800, Cash: 50 },
      transfers_out_bank: 200, transfers_in_bank: 0, bank_balance: 4500,
    })),
    http.get('/api/v1/assets/:year', ({ request }) => {
      assetAsOf = new URL(request.url).searchParams.get('as_of');
      const cutoff = assetAsOf ?? `${year}-${String(month).padStart(2, '0')}-01`;
      return HttpResponse.json([
        { asset_type: 'saving', asset_name: 'SavingAccount', computed_amount: 10000, manual_override: null, final_amount: 10000 },
        pensionAsset(cutoff),
      ]);
    }),
  );
});

test('Dashboard month controls have accessible names and 44px targets', async () => {
  render(<DashboardPage />, { wrapper });
  for (const name of ['Previous month', 'Next month']) expect(screen.getByRole('button', { name })).toHaveClass('min-h-11', 'min-w-11');
});

test('DashboardPage renders without crashing', async () => {
  render(<DashboardPage />, { wrapper });
  await waitFor(() => expect(screen.getByText(/bank balance/i)).toBeInTheDocument());
});

test('DashboardPage shows current month income and outcomes', async () => {
  render(<DashboardPage />, { wrapper });
  await waitFor(() => expect(screen.getByText(/income/i)).toBeInTheDocument());
  expect(screen.getByText(/3\.000/)).toBeInTheDocument();
  expect(screen.getByText('Visa')).toBeInTheDocument();
  expect(screen.getByText(/800/)).toBeInTheDocument();
});

test('DashboardPage shows bank balance for current month', async () => {
  render(<DashboardPage />, { wrapper });
  await waitFor(() => expect(screen.getByText(/4\.500/)).toBeInTheDocument());
  expect(screen.getByText('-€200,00')).toHaveClass('text-red-700', 'dark:text-red-300');
});

test('DashboardPage shows total incomes', async () => {
  render(<DashboardPage />, { wrapper });
  await waitFor(() => expect(screen.getByText(/3\.000/)).toBeInTheDocument());
});

test('DashboardPage includes accessible bank balance trend and transaction shortcut', async () => {
  render(<DashboardPage />, { wrapper });
  expect(await screen.findByRole('img', { name: /monthly bank balance trend/i })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /add transaction/i })).toHaveAttribute('href', '/transactions?add=1');
  expect(screen.getByRole('list', { name: /monthly bank balance values/i })).toHaveTextContent(/selected month/i);
});

test('Dashboard selects an explicit projection month and renders backend-derived pension provenance', async () => {
  const user = userEvent.setup();
  render(<DashboardPage />, { wrapper });
  await navigateDashboardTo(user, '2026-10-01');
  await waitFor(() => expect(assetAsOf).toBe('2026-10-01'));
  expect(await screen.findByText(/Statement balance €20\.000,00 through 2026-03-01; projected through 2026-10-01/)).toBeInTheDocument();
  expect(screen.getByText(/Employee €175,00 · Employer €350,00 · TFR €1\.400,00 · transfers €0,00/)).toBeInTheDocument();
  expect(screen.getAllByText(/21\.925/).length).toBeGreaterThan(0);
});

test('Dashboard shows exact snapshot-month balance and later-month projection after refetch', async () => {
  const user = userEvent.setup();
  render(<DashboardPage />, { wrapper });
  await navigateDashboardTo(user, statementMonth);
  await waitFor(() => expect(assetAsOf).toBe(statementMonth));
  expect(await screen.findByText(/Statement balance €20\.000,00 through 2026-03-01; projected through 2026-03-01/)).toBeInTheDocument();
  expect(screen.getAllByText(/20\.000/).length).toBeGreaterThan(0);
  expect(screen.getByText(/Employee €0,00 · Employer €0,00 · TFR €0,00 · transfers €0,00/)).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Next month' }));
  await waitFor(() => expect(assetAsOf).toBe('2026-04-01'));
  expect(await screen.findByText(/Statement balance €20\.000,00 through 2026-03-01; projected through 2026-04-01/)).toBeInTheDocument();
  expect(screen.getAllByText(/20\.275/).length).toBeGreaterThan(0);
  expect(screen.getByText(/Employee €25,00 · Employer €50,00 · TFR €200,00 · transfers €0,00/)).toBeInTheDocument();
});
