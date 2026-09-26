import { useQuery } from '@tanstack/react-query';
import { CartesianGrid, Line, LineChart, ReferenceDot, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { summaryApi } from '../../api/summary';
import { queryKeys } from '../../api/queryKeys';
import type { MonthlySummary } from '../../types/api';
import { fmt } from '../../utils/format';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
export const BANK_BALANCE_LINE_COLOR = 'var(--color-chart-line)';

export function formatBalanceTick(value: number): string {
  const absValue = Math.abs(value);
  const sign = value < 0 ? '−' : '';
  if (absValue < 1000) return `${sign}€${Math.round(absValue).toLocaleString('en-US')}`;
  const thousands = (absValue / 1000).toLocaleString('en-US', { maximumFractionDigits: 1 });
  return `${sign}€${thousands}k`;
}

export default function BankBalanceTrend({ year, selectedMonth }: { year: number; selectedMonth: number }) {
  const { data: months = [], isLoading } = useQuery({
    queryKey: queryKeys.summary.year(year),
    queryFn: () => summaryApi.year(year),
  });
  const data = Array.from({ length: 12 }, (_, index) => {
    const month: MonthlySummary | undefined = months.find((entry) => entry.month === index + 1);
    return { month: MONTHS[index], balance: month?.bank_balance ?? null, monthNumber: index + 1 };
  });
  const selected = data.find((entry) => entry.monthNumber === selectedMonth);

  return (
    <section aria-labelledby="balance-trend-title" className="bg-surface rounded-xl border border-line p-4 sm:p-6">
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="balance-trend-title" className="font-semibold text-primary">Bank balance trend</h2>
        <span className="text-sm text-secondary">{year}</span>
      </div>
      {isLoading ? <div className="h-48 mt-4 animate-pulse rounded bg-muted-bg" aria-label="Loading bank balance trend" /> : (
        <>
          <div className="h-56 mt-4" role="img" aria-label={`Monthly bank balance trend for ${year}. ${selected?.month ?? 'Selected month'} selected.`}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data} margin={{ top: 12, right: 12, bottom: 4, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-line)" />
                <XAxis dataKey="month" tick={{ fill: 'var(--color-secondary)', fontSize: 12 }} />
                <YAxis width={64} tickFormatter={formatBalanceTick} tick={{ fill: 'var(--color-secondary)', fontSize: 11 }} />
                <Tooltip formatter={(value) => value == null ? 'No data' : `€${fmt(Number(value))}`} />
                <Line type="monotone" dataKey="balance" name="Bank balance" stroke={BANK_BALANCE_LINE_COLOR} strokeWidth={2.5} connectNulls={false} dot={{ r: 3 }} activeDot={{ r: 5 }} />
                {selected?.balance !== null && selected?.balance !== undefined && <ReferenceDot x={selected.month} y={selected.balance} r={6} fill="#b45309" stroke="white" strokeWidth={2} />}
              </LineChart>
            </ResponsiveContainer>
          </div>
          <p className="sr-only">Monthly bank balance values:</p>
          <ul className="sr-only" aria-label={`Monthly bank balance values for ${year}`}>
            {data.map(({ month, balance, monthNumber }) => <li key={month} aria-current={monthNumber === selectedMonth ? 'date' : undefined}>{month}: {balance === null ? 'No data' : `€${fmt(balance)}`}{monthNumber === selectedMonth ? ' (selected month)' : ''}</li>)}
          </ul>
        </>
      )}
    </section>
  );
}
