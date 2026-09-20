import type { MonthlySummary } from '../../types/api';
import { fmt } from '../../utils/format';

interface Props { summary: MonthlySummary | undefined; isLoading: boolean; }

export default function BankBalanceCard({ summary, isLoading }: Props) {
  if (isLoading) return <div className="bg-surface rounded-lg border border-line p-6 animate-pulse h-32" />;
  const totalOutcomes = Object.values(summary?.outcomes_by_method ?? {}).reduce((s, v) => s + v, 0);
  return (
    <div className="bg-surface rounded-lg border border-line p-6">
      <p className="text-sm text-muted">Bank balance</p>
      <p className="text-3xl font-bold text-blue-700 mt-1">
        €{fmt(summary?.bank_balance ?? 0)}
      </p>
      <div className="mt-3 flex gap-6 text-sm flex-wrap">
        <div>
          <span className="text-muted">Income </span>
          <span className="text-green-600 font-medium">+€{fmt(summary?.incomes ?? 0)}</span>
        </div>
        <div>
          <span className="text-muted">Purchases & payments </span>
          <span className={`${totalOutcomes < 0 ? 'text-green-600' : 'text-red-500'} font-medium`}>
            {totalOutcomes < 0 ? '+' : '-'}€{fmt(Math.abs(totalOutcomes))}
          </span>
        </div>
        <div>
          <span className="text-muted">Transfers out </span>
          <span className="text-red-500 font-medium">-€{fmt(summary?.transfers_out_bank ?? 0)}</span>
        </div>
      </div>
    </div>
  );
}
