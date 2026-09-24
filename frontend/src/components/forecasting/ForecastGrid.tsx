import type { ForecastProjection } from '../../types/api';
import { fmt } from '../../utils/format';
import { Button } from '../ui/Button';

interface Props {
  projection: ForecastProjection;
  onAddAdjustment: (lineId: string) => void;
}

export default function ForecastGrid({ projection, onAddAdjustment }: Props) {
  const months = projection.monthly_totals.map((m) => m.month);

  return (
    <div>
      <div className="overflow-x-auto max-h-[70vh]">
      <table className="text-sm border-collapse min-w-full">
        <thead>
          <tr>
            <th className="p-2 text-left bg-subtle border border-line sticky left-0 min-w-40 text-primary">Line</th>
            {months.map((m) => (
              <th key={m} className="p-2 text-center bg-subtle border border-line min-w-20 text-xs text-primary">{m.slice(5)}</th>
            ))}
            <th className="p-2 text-right bg-subtle border border-line min-w-24 text-primary">Total</th>
          </tr>
        </thead>
        <tbody>
          {projection.lines.map((line) => {
            const lineTotal = line.months.reduce((s, m) => s + m.effective_amount, 0);
            const firstAdjustmentValidFrom = line.adjustments.reduce<string | null>(
              (earliest, adjustment) =>
                earliest === null || adjustment.valid_from < earliest
                  ? adjustment.valid_from
                  : earliest,
              null
            );
            return (
              <tr key={line.line_id} className="hover:bg-blue-50/30 dark:hover:bg-blue-900/10">
                <td className="p-2 border border-line sticky left-0 bg-surface text-primary">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium truncate">{line.detail}</span>
                    <Button variant="ghost" className="text-xs px-1 shrink-0" onClick={() => onAddAdjustment(line.line_id)}>
                      +adj
                    </Button>
                  </div>
                  {line.adjustments.length > 0 && (
                    <div className="text-xs text-yellow-600 dark:text-yellow-400 mt-0.5">{line.adjustments.length} adj.</div>
                  )}
                </td>
                {line.months.map((cell) => {
                  const hasAdj = firstAdjustmentValidFrom !== null && firstAdjustmentValidFrom.slice(0, 7) <= cell.month;
                  return (
                    <td key={cell.month} className={`p-2 border border-line text-right tabular-nums text-primary ${hasAdj ? 'text-yellow-700 dark:text-yellow-400 font-medium' : ''}`}>
                      {fmt(cell.effective_amount)}
                    </td>
                  );
                })}
                <td className="p-2 border border-line text-right tabular-nums font-semibold text-primary">{fmt(lineTotal)}</td>
              </tr>
            );
          })}
          <tr className="bg-blue-50 dark:bg-blue-900/20 font-semibold">
            <td className="p-2 border border-line sticky left-0 bg-blue-50 dark:bg-blue-900/20 text-primary">Monthly commitments</td>
            {projection.monthly_totals.map((mt) => (
              <td key={mt.month} className="p-2 border border-line text-right tabular-nums text-primary">{fmt(mt.total)}</td>
            ))}
            <td className="p-2 border border-line text-right tabular-nums text-primary">
              {fmt(projection.yearly_totals.reduce((s, y) => s + y.total, 0))}
            </td>
          </tr>
        </tbody>
        <tfoot>
          <tr className="bg-subtle">
            <td colSpan={months.length + 2} className="p-2 border border-line text-primary">
              <div className="flex gap-4">
                {projection.yearly_totals.map((yt) => (
                  <span key={yt.year} className="text-sm">
                    <strong>{yt.year}:</strong> €{fmt(yt.total)}
                  </span>
                ))}
              </div>
            </td>
          </tr>
        </tfoot>
      </table>
      </div>
      <p className="text-xs text-faint mt-1 sm:hidden">← Swipe to scroll all months</p>
    </div>
  );
}
