import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { summaryApi } from '../api/summary';
import { queryKeys } from '../api/queryKeys';
import { fmt } from '../utils/format';
const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

export default function SummaryPage() {
  const [year, setYear] = useState(() => new Date().getFullYear());
  const [inputYear, setInputYear] = useState(() => String(new Date().getFullYear()));
  const [mobileMonth, setMobileMonth] = useState(() => new Date().getMonth());
  const navigate = useNavigate();

  const { data: months = [], isLoading } = useQuery({
    queryKey: queryKeys.summary.year(year),
    queryFn: () => summaryApi.year(year),
  });

  // Collect all payment method names across all months
  const allMethods = Array.from(
    new Set(months.flatMap((m) => Object.keys(m.outcomes_by_method ?? {})))
  );

  const rows = [
    { label: 'Bank balance', values: months.map((m) => fmt(m.bank_balance)), highlight: true },
    { label: 'Incomes', values: months.map((m) => fmt(m.incomes)), highlight: false },
    ...allMethods.map((method) => ({
      label: method,
      values: months.map((m) => fmt(m.outcomes_by_method[method] ?? 0)),
      highlight: false,
    })),
    { label: 'Transfers out', values: months.map((m) => fmt(m.transfers_out_bank)), highlight: false },
    { label: 'Transfers in', values: months.map((m) => fmt(m.transfers_in_bank ?? 0)), highlight: false },
    { label: 'Stamp duty', values: months.map((m) => fmt(m.stamp_duty ?? 0)), highlight: false },
  ];

  const currentMonth = new Date().getMonth() + 1;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4">
        <h1 className="text-xl font-bold text-primary">Monthly Summary</h1>
        <input
          type="number"
          aria-label="Summary year"
          value={inputYear}
          onChange={(e) => {
            setInputYear(e.target.value);
            const parsed = parseInt(e.target.value, 10);
            if (!isNaN(parsed) && parsed >= 2000 && parsed <= 2100) {
              setYear(parsed);
              setMobileMonth(0);
            }
          }}
          className="border border-line-strong rounded px-2 py-1 min-h-11 w-24 text-sm bg-elevated text-primary"
          min="2000"
          max="2100"
        />
      </div>

      {isLoading && (
        <div className="animate-pulse h-48 bg-muted-bg rounded" />
      )}

      {/* Mobile view — one month at a time */}
      {!isLoading && (
        <div className="block sm:hidden space-y-3">
          {/* Month navigator */}
          <div className="flex items-center justify-between bg-surface border border-line rounded-lg px-4 py-2">
            <button
              aria-label="Previous month"
              onClick={() => setMobileMonth((m) => Math.max(0, m - 1))}
              disabled={mobileMonth === 0}
              className="px-3 py-2 min-h-11 min-w-11 text-secondary disabled:opacity-30 hover:text-primary"
            >
              ‹
            </button>
            <span className="font-medium text-primary">{MONTHS[mobileMonth]} {year}</span>
            <button
              aria-label="Next month"
              onClick={() => setMobileMonth((m) => Math.min(11, m + 1))}
              disabled={mobileMonth === 11}
              className="px-3 py-2 min-h-11 min-w-11 text-secondary disabled:opacity-30 hover:text-primary"
            >
              ›
            </button>
          </div>
          {/* Month data */}
          <div className="bg-surface border border-line rounded-lg divide-y divide-line">
            {rows.map((row) => (
              <button
                type="button"
                key={row.label}
                aria-label={`${row.label} for ${MONTHS[mobileMonth]} ${year}: ${row.values[mobileMonth] ?? 'no data'}. View filtered transactions`}
                className={`w-full flex justify-between items-center px-4 py-3 min-h-12 text-sm text-left hover:bg-blue-50 dark:hover:bg-blue-900/20 focus-visible:outline focus-visible:outline-2 focus-visible:outline-inset focus-visible:outline-blue-700 ${row.highlight ? 'bg-blue-50 dark:bg-blue-900/20 font-semibold' : ''}`}
                onClick={() => months[mobileMonth] && navigate(`/transactions?billing_month=${year}-${String(mobileMonth + 1).padStart(2, '0')}-01`)}
              >
                <span className="text-secondary">{row.label}</span>
                <span className="tabular-nums text-primary">{row.values[mobileMonth] ?? '—'}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Desktop view — full table */}
      {!isLoading && (
        <div className="hidden sm:block overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr>
                <th role="columnheader" className="text-left p-2 bg-subtle border border-line font-medium sticky left-0 min-w-36 text-primary">
                  {year}
                </th>
                {MONTHS.map((m, i) => (
                  <th
                    key={m}
                    role="columnheader"
                    className={`p-2 border border-line text-center font-medium min-w-24 text-primary ${i + 1 === currentMonth ? 'bg-blue-50 dark:bg-blue-900/30' : 'bg-subtle'}`}
                  >
                    {m}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.label} className={row.highlight ? 'bg-blue-50 dark:bg-blue-900/20 font-semibold' : ''}>
                  <td className="p-2 border border-line sticky left-0 bg-surface font-medium text-secondary">{row.label}</td>
                  {Array.from({ length: 12 }, (_, i) => {
                    const val = row.values[i];
                    const monthData = months[i];
                    return (
                      <td key={i} className={`p-0 border border-line text-right tabular-nums text-primary ${i + 1 === currentMonth ? 'bg-blue-50/30 dark:bg-blue-900/10' : ''}`}>
                        <button
                          type="button"
                          aria-label={`${row.label}, ${MONTHS[i]} ${year}: ${val ?? 'no data'}. View filtered transactions`}
                          disabled={!monthData}
                          className="w-full min-h-11 px-2 hover:bg-blue-50 dark:hover:bg-blue-900/20 focus-visible:outline focus-visible:outline-2 focus-visible:outline-inset focus-visible:outline-blue-700 disabled:cursor-default"
                          onClick={() => monthData && navigate(`/transactions?billing_month=${year}-${String(i + 1).padStart(2, '0')}-01`)}
                        >{val ?? '—'}</button>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
