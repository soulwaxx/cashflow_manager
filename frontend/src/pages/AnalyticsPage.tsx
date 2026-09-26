import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { analyticsApi } from '../api/analytics';
import { categoriesApi } from '../api/categories';
import { paymentMethodsApi } from '../api/paymentMethods';
import { queryKeys } from '../api/queryKeys';
import AnalyticsFilters from '../components/analytics/AnalyticsFilters';
import CategoryBarChart from '../components/analytics/CategoryBarChart';
import CumulativeLineChart from '../components/analytics/CumulativeLineChart';
import { Button } from '../components/ui/Button';
import type { AnalyticsCategoryRow } from '../types/api';

type View = 'bar' | 'cumulative';
type FilterDirection = 'debit' | 'income' | 'credit' | 'all';
interface Filters {
  from: string;
  to: string;
  direction: FilterDirection;
  categoryIds: string[];
  paymentMethodIds: string[];
}

export default function AnalyticsPage() {
  const [view, setView] = useState<View>('bar');
  const [filters, setFilters] = useState<Filters>(() => {
    const y = new Date().getFullYear();
    return {
      from: `${y}-01`,
      to: `${y}-12`,
      direction: 'all',
      categoryIds: [],
      paymentMethodIds: [],
    };
  });

  const { data: categoryRows = [] } = useQuery({
    queryKey: queryKeys.analytics.categoryRows(filters),
    queryFn: () =>
      analyticsApi.categories({
        from: filters.from,
        to: filters.to,
        direction: filters.direction,
        ...(filters.categoryIds.length ? { category_ids: filters.categoryIds.join(',') } : {}),
        ...(filters.paymentMethodIds.length ? { payment_method_ids: filters.paymentMethodIds.join(',') } : {}),
      }),
  });

  const { data: transferRows = [] } = useQuery({
    queryKey: queryKeys.analytics.transferRows(filters.from, filters.to),
    queryFn: () => analyticsApi.transfers({ from: filters.from, to: filters.to }),
  });

  const { data: categories = [] } = useQuery({
    queryKey: queryKeys.categories.list('all'),
    queryFn: () => categoriesApi.list(false),
  });
  const { data: paymentMethods = [] } = useQuery({
    queryKey: queryKeys.paymentMethods.list('all'),
    queryFn: () => paymentMethodsApi.list(false),
  });

  // Convert transfer rows into AnalyticsCategoryRow entries so the existing
  // chart components can render them without modification. The category_id is
  // set to the desired display label so the chart's fallback path
  // (categoryMap[id] ?? id) shows a readable, type-qualified series name.
  // Transfers are neither expenses nor income so they are hidden when the user
  // has set a direction filter — only shown in the "all" (unfiltered) view.
  const transferAsRows = useMemo<AnalyticsCategoryRow[]>(() => {
    if (filters.direction !== 'all') return [];
    return transferRows.map((t) => ({
      category_id: `→ ${t.to_account_name} (${t.to_account_type})`,
      type: t.to_account_type,
      sub_type: 'transfer',
      month: t.month,
      total_amount: t.total_amount,
    }));
  }, [transferRows, filters.direction]);

  const rows = useMemo(
    () => [...categoryRows, ...transferAsRows],
    [categoryRows, transferAsRows],
  );
  const categoryLabels = useMemo(() => Object.fromEntries(categories.map((category) => [category.id, `${category.type}/${category.sub_type}`])), [categories]);
  const textRows = useMemo(() => {
    const totals = new Map<string, number>();
    for (const row of rows) {
      const key = `${row.month}|${categoryLabels[row.category_id] ?? row.category_id}`;
      totals.set(key, (totals.get(key) ?? 0) + row.total_amount);
    }
    const labels = Array.from(new Set(rows.map((row) => categoryLabels[row.category_id] ?? row.category_id)));
    const months = Array.from(new Set(rows.map((row) => row.month))).sort();
    const running = new Map<string, number>();
    return months.flatMap((month) => labels.map((label) => {
      const amount = totals.get(`${month}|${label}`) ?? 0;
      const total = view === 'cumulative' ? (running.get(label) ?? 0) + amount : amount;
      running.set(label, total);
      return { month, label, total };
    }));
  }, [rows, categoryLabels, view]);

  return (
    <div className="max-w-6xl space-y-5">
      <h1 className="text-xl font-bold text-primary">Analytics</h1>
      <AnalyticsFilters
        filters={filters}
        categories={categories}
        paymentMethods={paymentMethods}
        onChange={setFilters}
      />
      <div className="flex flex-wrap gap-2" role="group" aria-label="Chart view">
        <Button aria-pressed={view === 'bar'} variant={view === 'bar' ? 'primary' : 'secondary'} onClick={() => setView('bar')}>Bar chart</Button>
        <Button aria-pressed={view === 'cumulative'} variant={view === 'cumulative' ? 'primary' : 'secondary'} onClick={() => setView('cumulative')}>Cumulative</Button>
      </div>
      <div className="bg-surface rounded-xl border border-line p-3 sm:p-5 min-w-0">
        {rows.length === 0 ? (
          <p className="text-faint text-sm text-center py-12">No data for selected filters</p>
        ) : view === 'bar' ? (
          <CategoryBarChart data={rows} categories={categories} />
        ) : (
          <CumulativeLineChart data={rows} categories={categories} />
        )}
        {rows.length > 0 && (
          <details className="mt-5 border-t border-line pt-4 text-sm" open>
            <summary className="font-medium text-secondary cursor-pointer rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600">{view === 'cumulative' ? 'Cumulative chart data by month' : 'Chart data by month'}</summary>
            <ul className="mt-3 grid gap-2 sm:grid-cols-2">
              {textRows.map((row) => (
                <li key={`${row.month}-${row.label}`} className="flex flex-wrap justify-between gap-x-3 rounded-lg bg-subtle px-3 py-2 text-secondary">
                  <span className="min-w-0 break-words">{row.month} · {row.label}</span>
                  <strong className="tabular-nums text-primary">€{row.total.toLocaleString('it-IT', { minimumFractionDigits: 2 })}</strong>
                </li>
              ))}
            </ul>
          </details>
        )}
      </div>
    </div>
  );
}
