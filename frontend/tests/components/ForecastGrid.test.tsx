import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import ForecastGrid from '../../src/components/forecasting/ForecastGrid';
import type { ForecastProjection } from '../../src/types/api';

const months = Array.from({ length: 12 }, (_, index) => `2026-${String(index + 1).padStart(2, '0')}`);

const projection: ForecastProjection = {
  forecast_id: 'f1',
  base_year: 2025,
  projection_years: 1,
  period: { from: '2026-01', to: '2026-12' },
  lines: [
    {
      line_id: 'l1',
      detail: 'Rent',
      category_id: null,
      base_amount: 900,
      billing_day: 1,
      adjustments: [],
      months: months.map((month) => ({ month, effective_amount: 900 })),
    },
  ],
  monthly_totals: months.map((month) => ({ month, total: 900 })),
  yearly_totals: [{ year: 2026, total: 10800 }],
};

test('ForecastGrid renders line details and effective amounts', () => {
  const qc = new QueryClient();
  render(
    <QueryClientProvider client={qc}>
      <ForecastGrid projection={projection} onAddAdjustment={() => {}} />
    </QueryClientProvider>
  );
  expect(screen.getByText('Rent')).toBeInTheDocument();
  expect(screen.getAllByText('900,00').length).toBeGreaterThan(0);
});

test('ForecastGrid shows yearly total', () => {
  const qc = new QueryClient();
  render(
    <QueryClientProvider client={qc}>
      <ForecastGrid projection={projection} onAddAdjustment={() => {}} />
    </QueryClientProvider>
  );
  expect(screen.getAllByText(/10\.800/).length).toBeGreaterThan(0);
});

test('ForecastGrid highlights months after the first adjustment threshold', () => {
  const qc = new QueryClient();
  const projectionWithAdjustment: ForecastProjection = {
    ...projection,
    lines: [
      {
        ...projection.lines[0],
        adjustments: [
          { id: 'adj-2', valid_from: '2026-02-01', new_amount: 950, adjustment_type: 'fixed' },
          { id: 'adj-1', valid_from: '2026-01-01', new_amount: 925, adjustment_type: 'fixed' },
        ],
        months: months.map((month, index) => ({ month, effective_amount: index === 0 ? 925 : 950 })),
      },
    ],
    monthly_totals: months.map((month, index) => ({ month, total: index === 0 ? 925 : 950 })),
    yearly_totals: [{ year: 2026, total: 11375 }],
  };

  const { container } = render(
    <QueryClientProvider client={qc}>
      <ForecastGrid projection={projectionWithAdjustment} onAddAdjustment={() => {}} />
    </QueryClientProvider>
  );

  const highlightedCells = container.querySelectorAll('tbody td.text-yellow-700.font-medium');
  expect(highlightedCells).toHaveLength(12);
  expect(highlightedCells[0]).toHaveTextContent('925,00');
  expect(highlightedCells[1]).toHaveTextContent('950,00');
});
