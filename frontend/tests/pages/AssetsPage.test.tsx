import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';
import { AuthProvider } from '../../src/contexts/AuthContext';
import AssetsPage from '../../src/pages/AssetsPage';

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}><MemoryRouter><AuthProvider>{children}</AuthProvider></MemoryRouter></QueryClientProvider>
  );
}

const year = new Date().getFullYear();

beforeEach(() => {
  server.use(
    http.get(`/api/v1/assets/${year}`, () =>
      HttpResponse.json([
        { asset_type: 'saving', asset_name: 'EmergencyFund', account_id: 'account-1', computed_amount: 8000, manual_override: null, final_amount: 8000 },
        { asset_type: 'pension', asset_name: 'AXA', account_id: 'account-2', computed_amount: 3200, manual_override: 3500, final_amount: 3500 },
      ])
    )
  );
});

test('AssetsPage renders heading', async () => {
  render(<AssetsPage />, { wrapper });
  await waitFor(() => expect(screen.getByText('Assets')).toBeInTheDocument());
});

test('AssetsPage shows asset names and values', async () => {
  render(<AssetsPage />, { wrapper });
  await waitFor(() => expect(screen.getByText('EmergencyFund')).toBeInTheDocument());
  expect(screen.getByText('AXA')).toBeInTheDocument();
  // Computed amount for EmergencyFund: 8.000,00 (Italian locale) — may appear in multiple columns
  expect(screen.getAllByText(/8\.000/).length).toBeGreaterThan(0);
});

test('AssetsPage shows override value when present', async () => {
  render(<AssetsPage />, { wrapper });
  await waitFor(() => expect(screen.getByText('AXA')).toBeInTheDocument());
  // AXA has manual_override: 3500, displayed as "3.500,00 (manual)"
  expect(screen.getAllByText(/3\.500/).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/manual/i).length).toBeGreaterThan(0);
});

test('AssetsPage lists assets with computed and override amounts', async () => {
  render(<AssetsPage />, { wrapper });
  await waitFor(() => expect(screen.getByText('EmergencyFund')).toBeInTheDocument());
  expect(screen.getByText('AXA')).toBeInTheDocument();
  expect(screen.getAllByText(/manual/i).length).toBeGreaterThan(0);
});

test('AssetsPage shows year selector', async () => {
  render(<AssetsPage />, { wrapper });
  await waitFor(() => expect(screen.getByRole('spinbutton')).toBeInTheDocument());
});

test('AssetsPage add account creates a stable account', async () => {
  let requestBody: unknown;
  server.use(
    http.post('/api/v1/accounts', async ({ request }) => {
      requestBody = await request.json();
      return HttpResponse.json({ ok: true });
    })
  );
  const user = userEvent.setup();
  render(<AssetsPage />, { wrapper });

  await user.click(await screen.findByRole('button', { name: /add account/i }));
  await user.type(screen.getByLabelText(/account name/i), 'Emergency');
  await user.type(screen.getByLabelText(/opening balance/i), '1234');
  await user.click(screen.getByRole('button', { name: /^add$/i }));

  await waitFor(() => {
    expect(requestBody).toEqual({
      type: 'saving', name: 'Emergency', opening_balance: 1234,
    });
  });
});
