import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';
import { AuthProvider } from '../../src/contexts/AuthContext';
import ForecastingPage from '../../src/pages/ForecastingPage';
import type { Forecast } from '../../src/types/api';

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

const mockForecasts: Forecast[] = [
  { id: 'fc1', name: 'Budget 2026', base_year: 2026, projection_years: 3, user_id: 'u1', created_at: '2026-01-01T00:00:00', updated_at: '2026-01-01T00:00:00' },
  { id: 'fc2', name: 'Conservative', base_year: 2026, projection_years: 2, user_id: 'u1', created_at: '2026-01-01T00:00:00', updated_at: '2026-01-01T00:00:00' },
];

beforeEach(() => {
  server.use(
    http.get('/api/v1/forecasts', () => HttpResponse.json(mockForecasts)),
  );
});

test('ForecastingPage renders without crashing', async () => {
  render(<ForecastingPage />, { wrapper });
  await waitFor(() => expect(screen.getByRole('heading', { name: /spending commitment forecasts/i })).toBeInTheDocument());
});

test('ForecastingPage shows forecast list', async () => {
  render(<ForecastingPage />, { wrapper });
  await waitFor(() => expect(screen.getByText('Budget 2026')).toBeInTheDocument());
  expect(screen.getByText('Conservative')).toBeInTheDocument();
});

test('ForecastingPage shows base year and projection years for each forecast', async () => {
  render(<ForecastingPage />, { wrapper });
  await waitFor(() => expect(screen.getByText('Budget 2026')).toBeInTheDocument());
  // ForecastList renders "Base year: 2026 · 3 years projection" etc.
  expect(screen.getAllByText(/base year: 2026/i).length).toBeGreaterThanOrEqual(2);
});

test('ForecastingPage has New forecast button', async () => {
  render(<ForecastingPage />, { wrapper });
  await waitFor(() => expect(screen.getByRole('button', { name: /new forecast/i })).toBeInTheDocument());
});

test('ForecastingPage opens create modal when New forecast button clicked', async () => {
  const user = userEvent.setup();
  render(<ForecastingPage />, { wrapper });
  await waitFor(() => expect(screen.getByRole('button', { name: /new forecast/i })).toBeInTheDocument());
  await user.click(screen.getByRole('button', { name: /new forecast/i }));
  expect(screen.getByRole('dialog')).toBeInTheDocument();
  // Modal title is an h2 with "Create forecast"
  expect(screen.getByRole('heading', { name: /create forecast/i })).toBeInTheDocument();
});

test('forecast creation keeps the form open and shows API errors', async () => {
  const user = userEvent.setup();
  server.use(http.post('/api/v1/forecasts', () => HttpResponse.json({
    detail: [{ loc: ['body', 'base_year'], msg: 'Invalid base year' }],
  }, { status: 422 })));
  render(<ForecastingPage />, { wrapper });
  await user.click(screen.getByRole('button', { name: /new forecast/i }));
  const dialog = screen.getByRole('dialog');
  await user.type(within(dialog).getByRole('textbox', { name: /Forecast name/ }), 'Plan');
  await user.click(within(dialog).getByRole('button', { name: 'Create forecast' }));
  expect(await within(dialog).findByRole('alert')).toHaveTextContent(/highlighted fields/);
  expect(within(dialog).getByText('Invalid base year')).toBeInTheDocument();
  expect(dialog).toBeInTheDocument();
});

test('ForecastingPage shows empty state when no forecasts', async () => {
  server.use(
    http.get('/api/v1/forecasts', () => HttpResponse.json([])),
  );
  render(<ForecastingPage />, { wrapper });
  await waitFor(() => expect(screen.getByText(/no forecasts yet/i)).toBeInTheDocument());
});
