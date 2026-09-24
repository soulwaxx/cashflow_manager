import { render, screen, waitFor, within } from '@testing-library/react';
import { vi } from 'vitest';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { http, HttpResponse, delay } from 'msw';
import { server } from '../mocks/server';
import { AuthProvider } from '../../src/contexts/AuthContext';
import ForecastDetailPage from '../../src/pages/ForecastDetailPage';
import type { ForecastDetail, ForecastProjection } from '../../src/types/api';

function makeWrapper(forecastId = 'fc1') {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return (
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={[`/forecasting/${forecastId}`]}>
          <AuthProvider>
            <Routes>
              <Route path="/forecasting/:id" element={children} />
            </Routes>
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>
    );
  };
}

const mockForecast: ForecastDetail = {
  id: 'fc1',
  name: 'Budget 2026',
  base_year: 2026,
  projection_years: 3,
  user_id: 'u1',
  created_at: '2026-12-31T00:00:00',
  updated_at: '2026-12-31T00:00:00',
  lines: [{
    id: 'line1', source_transaction_id: 'tx1', detail: 'Rent', category_id: null,
    payment_method_id: null, base_amount: 800, billing_day: 1, notes: null, adjustments: [],
  }],
};

const projectedMonths = Array.from({ length: 36 }, (_, index) => {
  const year = 2027 + Math.floor(index / 12);
  const month = String(index % 12 + 1).padStart(2, '0');
  return `${year}-${month}`;
});

const mockProjection: ForecastProjection = {
  forecast_id: 'fc1',
  base_year: 2026,
  projection_years: 3,
  period: { from: '2027-01', to: '2029-12' },
  lines: [
    {
      line_id: 'line1',
      detail: 'Rent',
      category_id: null,
      base_amount: 800,
      billing_day: 1,
      adjustments: [],
      months: projectedMonths.map((month) => ({ month, effective_amount: 800 })),
    },
  ],
  monthly_totals: projectedMonths.map((month) => ({ month, total: 800 })),
  yearly_totals: [
    { year: 2027, total: 9600 },
    { year: 2028, total: 9600 },
    { year: 2029, total: 9600 },
  ],
};

beforeEach(() => {
  server.use(
    http.get('/api/v1/forecasts/fc1', () => HttpResponse.json(mockForecast)),
    http.get('/api/v1/forecasts/fc1/projection', () => HttpResponse.json(mockProjection)),
    http.get('/api/v1/payment-methods', () => HttpResponse.json([])),
    http.get('/api/v1/categories', () => HttpResponse.json([])),
  );
});

test('ForecastDetailPage renders without crashing and shows forecast name', async () => {
  render(<ForecastDetailPage />, { wrapper: makeWrapper() });
  await waitFor(() => expect(screen.getByText('Budget 2026')).toBeInTheDocument());
});

test('ForecastDetailPage shows base year and projection years', async () => {
  render(<ForecastDetailPage />, { wrapper: makeWrapper() });
  await waitFor(() => expect(screen.getByText('Budget 2026')).toBeInTheDocument());
  expect(screen.getByText(/base year: 2026/i)).toBeInTheDocument();
  expect(screen.getByText(/3-year projection/i)).toBeInTheDocument();
});

test('ForecastDetailPage shows forecast line detail in the grid', async () => {
  render(<ForecastDetailPage />, { wrapper: makeWrapper() });
  await waitFor(() => expect(screen.getAllByText('Rent')).toHaveLength(2));
});

test('ForecastDetailPage shows base_amount formatted in the grid', async () => {
  render(<ForecastDetailPage />, { wrapper: makeWrapper() });
  // Rent is 800 per month, formatted as "800,00" in Italian locale
  await waitFor(() => expect(screen.getAllByText(/800,00/).length).toBeGreaterThan(0));
});

test('ForecastDetailPage has an add-adjustment button for each line', async () => {
  render(<ForecastDetailPage />, { wrapper: makeWrapper() });
  await waitFor(() => expect(screen.getAllByText('Rent').length).toBeGreaterThan(0));
  // ForecastGrid renders a "+adj" button per line
  expect(screen.getByRole('button', { name: /\+adj/i })).toBeInTheDocument();
});

test('ForecastDetailPage clicking +adj opens AdjustmentModal', async () => {
  const user = userEvent.setup();
  render(<ForecastDetailPage />, { wrapper: makeWrapper() });
  await waitFor(() => expect(screen.getByRole('button', { name: /\+adj/i })).toBeInTheDocument());
  await user.click(screen.getByRole('button', { name: /\+adj/i }));
  expect(screen.getByRole('dialog')).toBeInTheDocument();
  // AdjustmentModal title is an h2 with "Add adjustment"
  expect(screen.getByRole('heading', { name: /add adjustment/i })).toBeInTheDocument();
});

test('ForecastDetailPage shows yearly totals in the footer', async () => {
  render(<ForecastDetailPage />, { wrapper: makeWrapper() });
  await waitFor(() => expect(screen.getAllByText('Rent').length).toBeGreaterThan(0));
  // Projection starts in the year after the base year.
  expect(screen.getByText(/2027:/)).toBeInTheDocument();
});

test('ForecastDetailPage repairs an imported line and creates and deletes a manual line', async () => {
  const user = userEvent.setup();
  let detail = structuredClone(mockForecast);
  const requests: unknown[] = [];
  server.use(
    http.get('/api/v1/forecasts/fc1', () => HttpResponse.json(detail)),
    http.put('/api/v1/forecasts/fc1/lines/line1', async ({ request }) => {
      const body = await request.json() as typeof detail.lines[0];
      requests.push(body);
      detail.lines[0] = { ...detail.lines[0], ...body };
      return HttpResponse.json(detail.lines[0]);
    }),
    http.post('/api/v1/forecasts/fc1/lines', async ({ request }) => {
      const body = await request.json() as typeof detail.lines[0];
      requests.push(body);
      detail.lines.push({ ...body, id: 'line2', source_transaction_id: null, adjustments: [] });
      return HttpResponse.json(detail.lines[1]);
    }),
    http.delete('/api/v1/forecasts/fc1/lines/line2', () => {
      detail.lines = detail.lines.filter((line) => line.id !== 'line2');
      return HttpResponse.json({ ok: true });
    }),
  );
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
  try {
    render(<ForecastDetailPage />, { wrapper: makeWrapper() });
    await screen.findByText(/Imported · editable snapshot/);
    await user.click(screen.getByRole('button', { name: 'Edit commitment' }));
    let dialog = screen.getByRole('dialog');
    await within(dialog).findByRole('textbox', { name: /Detail/ });
    await user.clear(within(dialog).getByRole('textbox', { name: /Detail/ }));
    await user.type(within(dialog).getByRole('textbox', { name: /Detail/ }), 'Repaired rent');
    await user.click(within(dialog).getByRole('button', { name: 'Save commitment' }));
    await screen.findByText('Repaired rent');
    expect(requests[0]).toMatchObject({ detail: 'Repaired rent', category_id: null, payment_method_id: null });

    await user.click(screen.getByRole('button', { name: /Add commitment/ }));
    dialog = screen.getByRole('dialog');
    await within(dialog).findByRole('textbox', { name: /Detail/ });
    await user.type(within(dialog).getByRole('textbox', { name: /Detail/ }), 'Insurance');
    await user.type(within(dialog).getByRole('spinbutton', { name: /Monthly amount/ }), '45.20');
    await user.click(within(dialog).getByRole('button', { name: 'Add commitment' }));
    await screen.findByText('Insurance');
    expect(requests[1]).toMatchObject({ detail: 'Insurance', base_amount: 45.2 });
    await user.click(screen.getAllByRole('button', { name: 'Delete commitment' })[1]);
    await waitFor(() => expect(screen.queryByText('Insurance')).not.toBeInTheDocument());
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining('0 adjustment(s)'));
  } finally {
    confirm.mockRestore();
  }
});

test('editing an imported line preserves references while options load', async () => {
  const user = userEvent.setup();
  const detail = structuredClone(mockForecast);
  detail.lines[0].category_id = 'cat1';
  detail.lines[0].payment_method_id = 'pm1';
  let submitted: unknown;
  server.use(
    http.get('/api/v1/forecasts/fc1', () => HttpResponse.json(detail)),
    http.get('/api/v1/categories', async () => {
      await delay(30);
      return HttpResponse.json([{ id: 'cat1', user_id: 'u1', type: 'Housing', sub_type: 'Rent', is_active: false }]);
    }),
    http.get('/api/v1/payment-methods', async () => {
      await delay(30);
      return HttpResponse.json([{
        id: 'pm1', user_id: 'u1', name: 'Bank', type: 'bank', is_main_bank: true,
        linked_bank_id: null, opening_balance: 0, is_active: false,
      }]);
    }),
    http.put('/api/v1/forecasts/fc1/lines/line1', async ({ request }) => {
      submitted = await request.json();
      return HttpResponse.json({ ...detail.lines[0], ...(submitted as object) });
    }),
  );
  render(<ForecastDetailPage />, { wrapper: makeWrapper() });
  await screen.findByText(/Imported · editable snapshot/);
  await user.click(screen.getByRole('button', { name: 'Edit commitment' }));
  const dialog = screen.getByRole('dialog');
  expect(await within(dialog).findByRole('combobox', { name: 'Category' })).toHaveValue('cat1');
  expect(within(dialog).getByRole('combobox', { name: 'Payment method' })).toHaveValue('pm1');
  await user.click(within(dialog).getByRole('button', { name: 'Save commitment' }));
  await waitFor(() => expect(submitted).toMatchObject({ category_id: 'cat1', payment_method_id: 'pm1' }));
});

test('ForecastDetailPage adds, edits and deletes an adjustment', async () => {
  const user = userEvent.setup();
  let detail = structuredClone(mockForecast);
  const base = '/api/v1/forecasts/fc1/lines/line1/adjustments';
  server.use(
    http.get('/api/v1/forecasts/fc1', () => HttpResponse.json(detail)),
    http.post(base, async ({ request }) => {
      const body = await request.json() as typeof detail.lines[0]['adjustments'][number];
      detail.lines[0].adjustments.push({ ...body, id: 'adj1' });
      return HttpResponse.json({ ...body, id: 'adj1', forecast_line_id: 'line1' });
    }),
    http.put(`${base}/adj1`, async ({ request }) => {
      const body = await request.json() as typeof detail.lines[0]['adjustments'][number];
      detail.lines[0].adjustments[0] = { ...detail.lines[0].adjustments[0], ...body };
      return HttpResponse.json({ ...detail.lines[0].adjustments[0], forecast_line_id: 'line1' });
    }),
    http.delete(`${base}/adj1`, () => {
      detail.lines[0].adjustments = [];
      return HttpResponse.json({ ok: true });
    }),
  );
  render(<ForecastDetailPage />, { wrapper: makeWrapper() });
  await screen.findByText(/Imported · editable snapshot/);
  await user.click(screen.getByRole('button', { name: '+ Add adjustment' }));
  let dialog = screen.getByRole('dialog');
  await user.type(within(dialog).getByLabelText(/Start month/), '2027-06');
  await user.type(within(dialog).getByRole('spinbutton', { name: /New amount/ }), '900');
  await user.click(within(dialog).getByRole('button', { name: 'Add adjustment' }));
  await screen.findByText(/2027-06: €900/);
  await user.click(screen.getByRole('button', { name: 'Edit adjustment' }));
  dialog = screen.getByRole('dialog');
  await user.clear(within(dialog).getByRole('spinbutton', { name: /New amount/ }));
  await user.type(within(dialog).getByRole('spinbutton', { name: /New amount/ }), '950');
  await user.click(within(dialog).getByRole('button', { name: 'Save adjustment' }));
  await screen.findByText(/2027-06: €950/);
  await user.click(screen.getByRole('button', { name: 'Delete adjustment' }));
  await waitFor(() => expect(screen.queryByText(/2027-06: €950/)).not.toBeInTheDocument());
});

test('ForecastDetailPage keeps edits open and shows API validation errors', async () => {
  const user = userEvent.setup();
  server.use(http.put('/api/v1/forecasts/fc1/lines/line1', () => HttpResponse.json({
    detail: [{ loc: ['body', 'base_amount'], msg: 'Invalid amount' }],
  }, { status: 422 })));
  render(<ForecastDetailPage />, { wrapper: makeWrapper() });
  await screen.findByText(/Imported · editable snapshot/);
  await user.click(screen.getByRole('button', { name: 'Edit commitment' }));
  const dialog = screen.getByRole('dialog');
  await within(dialog).findByRole('button', { name: 'Save commitment' });
  await user.click(within(dialog).getByRole('button', { name: 'Save commitment' }));
  expect(await within(dialog).findByRole('alert')).toHaveTextContent(/correct the highlighted fields/);
  expect(within(dialog).getByText('Invalid amount')).toBeInTheDocument();
  expect(dialog).toBeInTheDocument();
});
