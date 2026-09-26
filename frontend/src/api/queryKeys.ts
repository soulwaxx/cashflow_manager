import type { QueryClient, QueryKey } from '@tanstack/react-query';

export const queryKeys = {
  auth: { config: ['auth', 'config'] as const, me: ['auth', 'me'] as const },
  onboarding: { status: ['onboarding', 'status'] as const },
  accounts: { all: ['accounts'] as const },
  categories: {
    all: ['categories'] as const,
    list: (scope: 'all' | 'active') => ['categories', scope] as const,
  },
  paymentMethods: {
    all: ['payment-methods'] as const,
    list: (scope: 'all' | 'active') => ['payment-methods', scope] as const,
  },
  transactions: {
    all: ['transactions'] as const,
    list: (scope: 'billing' | 'date', month: string) => ['transactions', scope, month] as const,
  },
  transfers: { all: ['transfers'] as const, paged: ['transfers', 'paged'] as const },
  summary: {
    all: ['summary'] as const,
    year: (year: number) => ['summary', year] as const,
    month: (year: number, month: number) => ['summary', year, month] as const,
  },
  assets: {
    all: ['assets'] as const,
    year: (year: number) => ['assets', year] as const,
    asOf: (year: number, asOf: string) => ['assets', year, asOf] as const,
  },
  analytics: {
    categories: ['analytics', 'categories'] as const,
    categoryRows: (filters: object) => ['analytics', 'categories', filters] as const,
    transfers: ['analytics', 'transfers'] as const,
    transferRows: (from: string, to: string) => ['analytics', 'transfers', from, to] as const,
  },
  salary: {
    all: ['salary'] as const,
    list: ['salary', 'list'] as const,
    calculations: ['salary', 'calculate'] as const,
    calculate: (params: object) => ['salary', 'calculate', params] as const,
  },
  taxConfig: { all: ['tax-config'] as const },
};

const dependencies = {
  tax: [queryKeys.taxConfig.all, queryKeys.salary.calculations],
  salary: [queryKeys.salary.all, queryKeys.assets.all, queryKeys.accounts.all],
  paymentMethod: [queryKeys.paymentMethods.all, queryKeys.summary.all],
  transaction: [queryKeys.transactions.all, queryKeys.summary.all, queryKeys.analytics.categories],
  transfer: [queryKeys.transfers.all, queryKeys.summary.all, queryKeys.assets.all, queryKeys.analytics.transfers],
  category: [queryKeys.categories.all, queryKeys.analytics.categories],
  account: [queryKeys.accounts.all, queryKeys.assets.all, queryKeys.analytics.transfers],
} satisfies Record<string, readonly QueryKey[]>;

export function invalidateFor(qc: QueryClient, domain: keyof typeof dependencies): void {
  for (const queryKey of dependencies[domain]) qc.invalidateQueries({ queryKey });
}

export function invalidateAssetOverride(qc: QueryClient, year: number): void {
  qc.invalidateQueries({ queryKey: queryKeys.assets.year(year) });
}
