import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';
import { AuthProvider } from '../../src/contexts/AuthContext';
import AnalyticsPage from '../../src/pages/AnalyticsPage';

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}><MemoryRouter><AuthProvider>{children}</AuthProvider></MemoryRouter></QueryClientProvider>
  );
}

const year = new Date().getFullYear();

beforeEach(() => {
  server.use(
    http.get('/api/v1/analytics/categories', () =>
      HttpResponse.json([
        { category_id: 'cat1', type: 'Personal', sub_type: 'Food', month: `${year}-01`, total_amount: 250 },
        { category_id: 'cat1', type: 'Personal', sub_type: 'Food', month: `${year}-02`, total_amount: 300 },
        { category_id: 'cat2', type: 'Leisure', sub_type: 'Restaurants', month: `${year}-01`, total_amount: 80 },
      ])
    ),
    http.get('/api/v1/categories', () =>
      HttpResponse.json([
        { id: 'cat1', type: 'Personal', sub_type: 'Food', is_active: true },
        { id: 'cat2', type: 'Leisure', sub_type: 'Restaurants', is_active: true },
      ])
    ),
    http.get('/api/v1/payment-methods', () => HttpResponse.json([])),
    http.get('/api/v1/analytics/transfers', () => HttpResponse.json([]))
  );
});

test('AnalyticsPage renders without crashing', async () => {
  render(<AnalyticsPage />, { wrapper });
  await waitFor(() => expect(screen.getByText(/analytics/i)).toBeInTheDocument());
});

test('AnalyticsPage shows chart tabs for bar and line views', async () => {
  render(<AnalyticsPage />, { wrapper });
  await waitFor(() => {
    expect(screen.getByRole('button', { name: /bar/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /cumulative/i })).toBeInTheDocument();
  });
});

test('AnalyticsPage chart renders category labels from mocked data', async () => {
  render(<AnalyticsPage />, { wrapper });
  // The Recharts Legend renders category labels as text nodes in the DOM.
  // Category labels are formatted as "type/sub_type" by the chart component.
  await waitFor(() => {
    expect(screen.getByText('Personal/Food')).toBeInTheDocument();
  });
  expect(screen.getByText('Leisure/Restaurants')).toBeInTheDocument();
});

test('AnalyticsPage switching to cumulative view changes active button variant', async () => {
  const user = userEvent.setup();
  render(<AnalyticsPage />, { wrapper });
  await waitFor(() => expect(screen.getByRole('button', { name: /cumulative/i })).toBeInTheDocument());

  const barBtn = screen.getByRole('button', { name: /bar/i });
  const cumBtn = screen.getByRole('button', { name: /cumulative/i });

  // Initially bar is primary (contains bg-blue-600), cumulative is secondary
  expect(barBtn.className).toMatch(/bg-blue-600/);
  expect(cumBtn.className).not.toMatch(/bg-blue-600/);

  await user.click(cumBtn);

  // After click, cumulative becomes primary and bar becomes secondary
  expect(cumBtn.className).toMatch(/bg-blue-600/);
  expect(barBtn.className).not.toMatch(/bg-blue-600/);
});

test('AnalyticsPage exposes filter state and text chart data to keyboard users', async () => {
  const user = userEvent.setup();
  render(<AnalyticsPage />, { wrapper });
  await screen.findByText('Chart data by month');
  expect(screen.getByText(`${year}-01 · Personal/Food`).closest('li')).toHaveTextContent('€250,00');
  const food = screen.getByRole('button', { name: 'Personal/Food' });
  expect(food).toHaveAttribute('aria-pressed', 'false');
  await user.click(food);
  expect(food).toHaveAttribute('aria-pressed', 'true');
  expect(screen.getByLabelText('Direction')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Cumulative' }));
  expect(screen.getByText('Cumulative chart data by month')).toBeInTheDocument();
  expect(screen.getByText(`${year}-02 · Personal/Food`).closest('li')).toHaveTextContent('€550,00');
});

test('AnalyticsPage initializes with current year range', async () => {
  render(<AnalyticsPage />, { wrapper });

  const expectedFrom = `${year}-01`;
  const expectedTo = `${year}-12`;

  await waitFor(() => {
    expect(screen.getByLabelText('From')).toHaveValue(expectedFrom);
    expect(screen.getByLabelText('To')).toHaveValue(expectedTo);
  });
});
