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

  return (
    <div className="max-w-5xl space-y-4">
      <h1 className="text-xl font-bold text-primary">Analytics</h1>
      <AnalyticsFilters
        filters={filters}
        categories={categories}
        paymentMethods={paymentMethods}
        onChange={setFilters}
      />
      <div className="flex gap-2">
        <Button variant={view === 'bar' ? 'primary' : 'secondary'} onClick={() => setView('bar')}>Bar chart</Button>
        <Button variant={view === 'cumulative' ? 'primary' : 'secondary'} onClick={() => setView('cumulative')}>Cumulative</Button>
      </div>
      <div className="bg-surface rounded-lg border border-line p-4">
        {rows.length === 0 ? (
          <p className="text-faint text-sm text-center py-12">No data for selected filters</p>
        ) : view === 'bar' ? (
          <CategoryBarChart data={rows} categories={categories} />
        ) : (
          <CumulativeLineChart data={rows} categories={categories} />
        )}
      </div>
    </div>
  );
}
