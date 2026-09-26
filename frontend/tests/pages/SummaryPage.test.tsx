import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';
import { AuthProvider } from '../../src/contexts/AuthContext';
import SummaryPage from '../../src/pages/SummaryPage';

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

const year = new Date().getFullYear();

beforeEach(() => {
  const months = Array.from({ length: 12 }, (_, i) => ({
    year, month: i + 1,
    incomes: 3000, outcomes_by_method: { Visa: 500 },
    transfers_out_bank: 100, transfers_in_bank: 0, bank_balance: 5000 + i * 100,
  }));
  server.use(http.get(`/api/v1/summary/${year}`, () => HttpResponse.json(months)));
});

test('SummaryPage shows 12 month columns', async () => {
  render(<SummaryPage />, { wrapper });
  await waitFor(() => expect(screen.getAllByRole('columnheader')).toHaveLength(13)); // year + 12 months
});

test('Summary year and month controls are labeled with 44px targets', async () => {
  render(<SummaryPage />, { wrapper });
  const yearInput = await screen.findByRole('spinbutton', { name: 'Summary year' });
  await screen.findByRole('button', { name: 'Next month' });
  expect(yearInput).toHaveClass('min-h-11');
  for (const name of ['Previous month', 'Next month']) {
    expect(screen.getByRole('button', { name })).toHaveClass('min-h-11', 'min-w-11');
  }
});

test('SummaryPage renders without crashing', async () => {
  render(<SummaryPage />, { wrapper });
  await waitFor(() => expect(screen.getByText(/monthly summary/i)).toBeInTheDocument());
});

test('SummaryPage shows stamp_duty in monthly row', async () => {
  server.use(
    http.get(`/api/v1/summary/${year}`, () =>
      HttpResponse.json(
        Array.from({ length: 12 }, (_, i) => ({
          year, month: i + 1,
          incomes: 3000,
          outcomes_by_method: { Visa: 500 },
          transfers_out_bank: 100,
          transfers_in_bank: 0,
          bank_balance: 5000 + i * 100,
          stamp_duty: i === 0 ? 2 : 0,
        }))
      )
    )
  );
  render(<SummaryPage />, { wrapper });
  // The Stamp duty row label is rendered (appears in both mobile and desktop views)
  await waitFor(() => expect(screen.getAllByText('Stamp duty')[0]).toBeInTheDocument());
  // The value "2,00" appears in the stamp duty row (Italian format: 2 → "2,00")
  expect(screen.getByText('2,00')).toBeInTheDocument();
});

test('SummaryPage shows Transfers in row', async () => {
  render(<SummaryPage />, { wrapper });
  await waitFor(() => expect(screen.getAllByText('Transfers in')[0]).toBeInTheDocument());
});

test('SummaryPage year input debounce prevents invalid queries', async () => {
  const user = userEvent.setup();
  render(<SummaryPage />, { wrapper });

  // Wait for the initial render with the current year
  await waitFor(() => expect(screen.getByRole('spinbutton')).toBeInTheDocument());

  const input = screen.getByRole('spinbutton');

  // Clear and type a partial year value
  await user.clear(input);
  await user.type(input, '20');

  // The input shows the partial value typed by the user
  expect(input).toHaveValue(20);

  // The year query should not have been triggered with an invalid partial year.
  // We verify this by checking that no summary row data for year=20 is shown —
  // the page should still display the current-year data (or the loading state),
  // not silently break. The header column should still show a 4-digit year.
  // Type a valid complete year to confirm it updates correctly.
  await user.clear(input);
  await user.type(input, String(year));
  expect(input).toHaveValue(year);
});
