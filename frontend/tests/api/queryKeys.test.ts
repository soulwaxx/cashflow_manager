import { describe, expect, it } from 'vitest';
import { QueryClient } from '@tanstack/react-query';
import { invalidateAssetOverride, invalidateFor, queryKeys } from '../../src/api/queryKeys';

const tracked = {
  auth: queryKeys.auth.me,
  tax: queryKeys.taxConfig.all,
  salary: queryKeys.salary.list,
  salaryCalculation: queryKeys.salary.calculate({ ral: 42000 }),
  methods: queryKeys.paymentMethods.list('active'),
  transactions: queryKeys.transactions.list('date', '2026-01'),
  transfers: queryKeys.transfers.paged,
  summary: queryKeys.summary.month(2026, 1),
  assets: queryKeys.assets.asOf(2026, '2026-01-01'),
  otherYearAssets: queryKeys.assets.asOf(2027, '2027-01-01'),
  categoryAnalytics: queryKeys.analytics.categoryRows({ from: '2026-01' }),
  transferAnalytics: queryKeys.analytics.transferRows('2026-01', '2026-12'),
  categories: queryKeys.categories.list('all'),
  accounts: queryKeys.accounts.all,
};

type Family = keyof typeof tracked;

function cache() {
  const qc = new QueryClient();
  for (const queryKey of Object.values(tracked)) qc.setQueryData(queryKey, { cached: true });
  return qc;
}

function assertInvalidated(qc: QueryClient, expected: Family[]) {
  for (const [family, queryKey] of Object.entries(tracked) as [Family, (typeof tracked)[Family]][]) {
    expect(qc.getQueryCache().find({ queryKey, exact: true })?.state.isInvalidated, family)
      .toBe(expected.includes(family));
  }
}

describe('mutation cache dependencies', () => {
  it.each([
    ['tax', ['tax', 'salaryCalculation']],
    ['salary', ['salary', 'salaryCalculation', 'assets', 'otherYearAssets', 'accounts']],
    ['paymentMethod', ['methods', 'summary']],
    ['transaction', ['transactions', 'summary', 'categoryAnalytics']],
    ['transfer', ['transfers', 'summary', 'assets', 'otherYearAssets', 'transferAnalytics']],
    ['category', ['categories', 'categoryAnalytics']],
    ['account', ['accounts', 'assets', 'otherYearAssets', 'transferAnalytics']],
  ] as const)('%s mutations invalidate only dependent query families', (mutation, affected) => {
    const qc = cache();
    invalidateFor(qc, mutation);
    assertInvalidated(qc, [...affected]);
  });

  it('asset override mutations refresh only the affected year', () => {
    const qc = cache();
    invalidateAssetOverride(qc, 2026);
    assertInvalidated(qc, ['assets']);
  });
});
