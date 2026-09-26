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
    <li className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-2 gap-y-1 py-3 border-b last:border-0 text-sm sm:flex">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-medium truncate text-primary">{tx.detail}</span>
          {tx.recurrence_months && (
            <span title="Recurring" className="text-blue-400 text-xs">↻</span>
          )}
        </div>
        <div className="text-muted text-xs mt-0.5">
          {tx.date}
          {tx.billing_month !== tx.date.slice(0, 7) + '-01' && (
            <span className="text-blue-800 dark:text-blue-300 ml-1" title="Credit card: billed in a different month">
              → billed {tx.billing_month.slice(0, 7)}
            </span>
          )}
        </div>
        <details className="sm:hidden mt-1 text-xs text-secondary">
          <summary className="cursor-pointer min-h-11 min-w-[5.5rem] px-2 inline-flex items-center">Details</summary>
          <p>Payment method: {method?.name ?? tx.payment_method_id ?? 'Deleted payment method'}</p>
          <p>Category: {category ? `${category.type}/${category.sub_type}` : 'Uncategorized'}</p>
          <div className="flex gap-2 mt-2">
            <Button variant="ghost" className="text-xs px-2 min-h-11 min-w-[2.75rem]" onClick={onEdit} title="Edit" aria-label={`Edit ${tx.detail}`}>Edit</Button>
            <Button variant="ghost" className="text-xs px-2 min-h-11 min-w-[2.75rem] text-red-700 dark:text-red-300" onClick={onDelete} title="Delete" aria-label={`Delete ${tx.detail}`}>Delete</Button>
          </div>
        </details>
        <div className="hidden sm:block text-muted text-xs mt-0.5">
          {method?.name ?? tx.payment_method_id ?? 'Deleted payment method'}
          {' · '}{category ? `${category.type}/${category.sub_type}` : 'Uncategorized'}
        </div>
      </div>
      <Badge color={directionColor}>
        {cashImpact.isSupported
          ? `${cashImpact.label} ${cashImpact.displaySign}€${fmt(tx.amount)}`
          : `${cashImpact.label} · €${fmt(tx.amount)} (no cash impact)`}
      </Badge>
      <div className="hidden sm:flex gap-1 shrink-0">
        <Button variant="ghost" className="text-xs px-2 min-h-11 min-w-[2.75rem]" onClick={onEdit} title="Edit" aria-label={`Edit ${tx.detail}`}>
          Edit
        </Button>
        <Button variant="ghost" className="text-xs px-2 min-h-11 min-w-[2.75rem] text-red-700 dark:text-red-300" onClick={onDelete} title="Delete" aria-label={`Delete ${tx.detail}`}>
          Delete
        </Button>
      </div>
    </li>
  );
}
