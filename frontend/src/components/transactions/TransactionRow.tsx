import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import type { Transaction, PaymentMethod, Category } from '../../types/api';
import { fmt } from '../../utils/format';
import { cashImpactForTransaction } from '../../utils/transactionSemantics';

interface Props {
  tx: Transaction;
  method?: PaymentMethod;
  category?: Category;
  onEdit: () => void;
  onDelete: () => void;
}

export default function TransactionRow({ tx, method, category, onEdit, onDelete }: Props) {
  const cashImpact = cashImpactForTransaction(method?.type, tx.transaction_direction);
  const directionColor = !cashImpact.isSupported ? 'gray' : cashImpact.displaySign === '+' ? 'green' : 'red';
  return (
    <li className="flex items-center gap-2 py-2 border-b last:border-0 text-sm">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-medium truncate text-primary">{tx.detail}</span>
          {tx.recurrence_months && (
            <span title="Recurring" className="text-blue-400 text-xs">↻</span>
          )}
        </div>
        <div className="text-muted text-xs mt-0.5">
          {tx.date}
          {tx.billing_month !== tx.date.slice(0, 7) + '-01' && (
            <span className="text-blue-500 ml-1" title="Credit card: billed in a different month">
              → billed {tx.billing_month.slice(0, 7)}
            </span>
          )}
          {' · '}{method?.name ?? tx.payment_method_id ?? 'Deleted payment method'}
          {' · '}{category ? `${category.type}/${category.sub_type}` : ''}
        </div>
      </div>
      <Badge color={directionColor}>
        {cashImpact.isSupported
          ? `${cashImpact.label} ${cashImpact.displaySign}€${fmt(tx.amount)}`
          : `${cashImpact.label} · €${fmt(tx.amount)} (no cash impact)`}
      </Badge>
      <div className="flex gap-1 shrink-0">
        <Button variant="ghost" className="text-xs px-1.5 min-w-[2rem]" onClick={onEdit} title="Edit">
          <span className="hidden sm:inline">Edit</span>
          <span className="sm:hidden" aria-hidden="true">✎</span>
        </Button>
        <Button variant="ghost" className="text-xs px-1.5 min-w-[2rem] text-red-500" onClick={onDelete} title="Delete">
          <span className="hidden sm:inline">Delete</span>
          <span className="sm:hidden" aria-hidden="true">✕</span>
        </Button>
      </div>
    </li>
  );
}
