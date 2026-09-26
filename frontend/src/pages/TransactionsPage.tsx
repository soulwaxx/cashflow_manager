import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import TransactionList from '../components/transactions/TransactionList';

function buildMonthOptions() {
  const months = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
  ];
  return months.map((label, i) => ({ value: String(i + 1).padStart(2, '0'), label }));
}

function buildYearOptions() {
  const currentYear = new Date().getFullYear();
  const years = [];
  for (let y = currentYear - 3; y <= currentYear + 1; y++) {
    years.push({ value: String(y), label: String(y) });
  }
  return years;
}

const MONTH_OPTIONS = buildMonthOptions();
const YEAR_OPTIONS = buildYearOptions();

export default function TransactionsPage() {
  const [searchParams] = useSearchParams();
  // billing_month URL param arrives as "YYYY-MM-DD" (from SummaryPage); extract "YYYY-MM"
  const billingMonthParam = searchParams.get('billing_month')?.slice(0, 7) ?? null;
  const openAddOnLoad = searchParams.get('add') === '1';

  const now = new Date();
  const initDate = billingMonthParam ? new Date(billingMonthParam + '-01T00:00:00') : now;

  const [year, setYear] = useState(String(initDate.getFullYear()));
  const [month, setMonth] = useState(String(initDate.getMonth() + 1).padStart(2, '0'));
  // Default to billing-month mode when navigated from Summary, otherwise actual-date mode
  const [mode, setMode] = useState<'date' | 'billing'>(billingMonthParam ? 'billing' : 'date');

  const yearMonth = `${year}-${month}`;

  return (
    <div className="max-w-3xl space-y-4">
      <div className="space-y-2">
        <h1 className="text-xl font-bold text-primary">Transactions</h1>
        <div className="flex items-center gap-2 flex-wrap">
          <select
            aria-label="Transaction year"
            value={year}
            onChange={(e) => setYear(e.target.value)}
            className="border border-line rounded px-2 py-1 min-h-11 text-sm bg-surface text-primary"
          >
            {YEAR_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
          <select
            aria-label="Transaction month"
            value={month}
            onChange={(e) => setMonth(e.target.value)}
            className="border border-line rounded px-2 py-1 min-h-11 text-sm bg-surface text-primary"
          >
            {MONTH_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
          <div className="flex rounded border border-line overflow-hidden text-sm">
            <button
              className={`px-3 py-2 min-h-11 ${mode === 'date' ? 'bg-blue-600 text-white' : 'bg-surface text-secondary hover:bg-subtle'}`}
              onClick={() => setMode('date')}
              title="Filter by the actual date the transaction occurred"
            >
              By date
            </button>
            <button
              className={`px-3 py-2 min-h-11 ${mode === 'billing' ? 'bg-blue-600 text-white' : 'bg-surface text-secondary hover:bg-subtle'}`}
              onClick={() => setMode('billing')}
              title="Filter by billing month — credit card charges appear in the month they are billed"
            >
              By billing month
            </button>
          </div>
        </div>
      </div>
      <TransactionList
        dateMonth={mode === 'date' ? yearMonth : undefined}
        billingMonth={mode === 'billing' ? yearMonth : undefined}
        initialAddOpen={openAddOnLoad}
      />
    </div>
  );
}
