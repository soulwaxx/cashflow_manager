import type { Category, PaymentMethod } from '../../types/api';

interface Filters {
  from: string;
  to: string;
  direction: 'debit' | 'income' | 'credit' | 'all';
  categoryIds: string[];
  paymentMethodIds: string[];
}

interface Props {
  filters: Filters;
  categories: Category[];
  paymentMethods: PaymentMethod[];
  onChange: (f: Filters) => void;
}

export default function AnalyticsFilters({ filters, categories, paymentMethods, onChange }: Props) {
  const toggleCat = (id: string) =>
    onChange({
      ...filters,
      categoryIds: filters.categoryIds.includes(id)
        ? filters.categoryIds.filter((c) => c !== id)
        : [...filters.categoryIds, id],
    });

  const togglePM = (id: string) =>
    onChange({
      ...filters,
      paymentMethodIds: filters.paymentMethodIds.includes(id)
        ? filters.paymentMethodIds.filter((p) => p !== id)
        : [...filters.paymentMethodIds, id],
    });

  return (
    <div className="bg-surface border border-line rounded-xl p-4 sm:p-5 space-y-4 text-sm">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div className="flex flex-col gap-1">
          <label htmlFor="analytics-from" className="text-xs text-muted font-medium">From</label>
          <input id="analytics-from" type="month" value={filters.from} onChange={(e) => onChange({ ...filters, from: e.target.value })}
            className="w-full min-w-0 min-h-11 border border-line-strong rounded-lg px-3 bg-elevated text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600" />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="analytics-to" className="text-xs text-muted font-medium">To</label>
          <input id="analytics-to" type="month" value={filters.to} onChange={(e) => onChange({ ...filters, to: e.target.value })}
            className="w-full min-w-0 min-h-11 border border-line-strong rounded-lg px-3 bg-elevated text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600" />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="analytics-direction" className="text-xs text-muted font-medium">Direction</label>
          <select id="analytics-direction" value={filters.direction} onChange={(e) => onChange({ ...filters, direction: e.target.value as Filters['direction'] })}
            className="w-full min-w-0 min-h-11 border border-line-strong rounded-lg px-3 bg-elevated text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600">
            <option value="all">All</option>
            <option value="debit">Debit</option>
            <option value="income">Income</option>
            <option value="credit">Credit</option>
          </select>
        </div>
      </div>
      {categories.length > 0 && (
        <div role="group" aria-label="Categories">
          <p className="text-xs text-muted font-medium mb-2">Categories</p>
          <div className="flex flex-wrap gap-2">
            {categories.map((c) => (
              <button
                key={c.id}
                onClick={() => toggleCat(c.id)}
                aria-pressed={filters.categoryIds.includes(c.id)}
                className={`min-h-11 px-3 py-2 rounded-full text-xs border focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600 ${filters.categoryIds.includes(c.id) ? 'bg-blue-600 text-white border-blue-600' : 'border-line-strong text-secondary'}`}
              >
                {c.type}/{c.sub_type}
              </button>
            ))}
          </div>
        </div>
      )}
      {paymentMethods.length > 0 && (
        <div role="group" aria-label="Payment methods">
          <p className="text-xs text-muted font-medium mb-2">Payment methods</p>
          <div className="flex flex-wrap gap-2">
            {paymentMethods.map((m) => (
              <button
                key={m.id}
                onClick={() => togglePM(m.id)}
                aria-pressed={filters.paymentMethodIds.includes(m.id)}
                className={`min-h-11 px-3 py-2 rounded-full text-xs border focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600 ${filters.paymentMethodIds.includes(m.id) ? 'bg-blue-600 text-white border-blue-600' : 'border-line-strong text-secondary'}`}
              >
                {m.name}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
