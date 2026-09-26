import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';
import { AuthProvider } from '../../src/contexts/AuthContext';
import DashboardPage from '../../src/pages/DashboardPage';

let assetAsOf: string | null;

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

beforeEach(() => {
  assetAsOf = null;
  const year = new Date().getFullYear();
  const month = new Date().getMonth() + 1;
  server.use(
    http.get(`/api/v1/summary/${year}`, () => HttpResponse.json([
      { year, month, incomes: 3000, outcomes_by_method: {}, transfers_out_bank: 0, transfers_in_bank: 0, bank_balance: 4500 },
    ])),
    http.get(`/api/v1/summary/${year}/${month}`, () =>
      HttpResponse.json({
        year, month,
        incomes: 3000,
        outcomes_by_method: { 'Visa': 800, 'Cash': 50 },
        transfers_out_bank: 200,
        transfers_in_bank: 0,
        bank_balance: 4500,
      })
    ),
    http.get(`/api/v1/assets/${year}`, ({ request }) => {
      assetAsOf = new URL(request.url).searchParams.get('as_of');
      return HttpResponse.json([
        { asset_type: 'saving', asset_name: 'SavingAccount', computed_amount: 10000, manual_override: null, final_amount: 10000 },
      ]);
    })
  );
});

test('Dashboard month controls have accessible names and 44px targets', async () => {
  render(<DashboardPage />, { wrapper });
  for (const name of ['Previous month', 'Next month']) {
    expect(screen.getByRole('button', { name })).toHaveClass('min-h-11', 'min-w-11');
  }
});

test('DashboardPage renders without crashing', async () => {
  render(<DashboardPage />, { wrapper });
  await waitFor(() => expect(screen.getByText(/bank balance/i)).toBeInTheDocument());
});

test('DashboardPage shows current month income and outcomes', async () => {
  render(<DashboardPage />, { wrapper });
  // Income label and formatted value from mocked data (3000 → "3.000,00")
  await waitFor(() => expect(screen.getByText(/income/i)).toBeInTheDocument());
  expect(screen.getByText(/3\.000/)).toBeInTheDocument();
  // Outcomes by method section shows the Visa entry (800 → "800,00")
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

test('DashboardPage requests assets as of the selected month', async () => {
  const current = new Date();
  const expectedAsOf = `${current.getFullYear()}-${String(current.getMonth() + 1).padStart(2, '0')}-01`;
  render(<DashboardPage />, { wrapper });
  await waitFor(() => expect(screen.getByText(/SavingAccount/i)).toBeInTheDocument());
  expect(assetAsOf).toBe(expectedAsOf);
});
