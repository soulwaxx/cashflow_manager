import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { transactionsApi } from '../../api/transactions';
import { paymentMethodsApi } from '../../api/paymentMethods';
import { categoriesApi } from '../../api/categories';
import { queryKeys, invalidateFor } from '../../api/queryKeys';
import TransactionRow from './TransactionRow';
import TransactionForm from './TransactionForm';
import CascadeDeleteModal from './CascadeDeleteModal';
import Modal from '../ui/Modal';
import { Button } from '../ui/Button';
import type { Transaction } from '../../types/api';

interface Props {
  dateMonth?: string;
  billingMonth?: string;
}

export default function TransactionList({ dateMonth, billingMonth }: Props) {
  const qc = useQueryClient();
  const [addOpen, setAddOpen] = useState(false);
  const [editTx, setEditTx] = useState<Transaction | null>(null);
  const [deleteTx, setDeleteTx] = useState<Transaction | null>(null);

  const { data: transactions = [], isLoading } = useQuery({
    queryKey: queryKeys.transactions.list(billingMonth ? 'billing' : 'date', (billingMonth ?? dateMonth) ?? ''),
    queryFn: () =>
      billingMonth
        ? transactionsApi.list({ billing_month: billingMonth })
        : transactionsApi.list({ date_month: dateMonth }),
  });
  const { data: methods = [] } = useQuery({ queryKey: queryKeys.paymentMethods.list('all'), queryFn: () => paymentMethodsApi.list(false) });
  const { data: categories = [] } = useQuery({ queryKey: queryKeys.categories.list('all'), queryFn: () => categoriesApi.list(false) });

  const methodMap = Object.fromEntries(methods.map((m) => [m.id, m]));
  const categoryMap = Object.fromEntries(categories.map((c) => [c.id, c]));

  const { mutate: deleteOne, isPending: deleteLoading } = useMutation({
    mutationFn: ({ id, cascade }: { id: string; cascade: string }) =>
      transactionsApi.delete(id, cascade),
    onSuccess: () => {
      invalidateFor(qc, 'transaction');
      setDeleteTx(null);
    },
  });

  if (isLoading) return <div className="animate-pulse h-32 bg-muted-bg rounded" />;

  return (
    <>
      <div className="flex justify-between items-center mb-3">
        <h2 className="font-semibold text-secondary">Transactions</h2>
        <Button onClick={() => setAddOpen(true)}>+ Add transaction</Button>
      </div>
      <ul className="bg-surface rounded-lg border border-line divide-y divide-line">
        {transactions.length === 0 && (
          <li className="p-4 text-sm text-faint">No transactions</li>
        )}
        {transactions.map((tx) => (
          <TransactionRow
            key={tx.id}
            tx={tx}
            method={tx.payment_method_id ? methodMap[tx.payment_method_id] : undefined}
            category={tx.category_id ? categoryMap[tx.category_id] : undefined}
            onEdit={() => setEditTx(tx)}
            onDelete={() => setDeleteTx(tx)}
          />
        ))}
      </ul>

      <Modal open={addOpen} onClose={() => setAddOpen(false)} title="Add transaction">
        <TransactionForm onSuccess={() => setAddOpen(false)} />
      </Modal>

      <Modal open={!!editTx} onClose={() => setEditTx(null)} title="Edit transaction">
        {editTx && (
          <TransactionForm initial={editTx} onSuccess={() => setEditTx(null)} />
        )}
      </Modal>

      <CascadeDeleteModal
        open={!!deleteTx}
        onClose={() => setDeleteTx(null)}
        isRecurring={!!deleteTx?.recurrence_months}
        isPending={deleteLoading}
        onConfirm={(cascade) => deleteTx && deleteOne({ id: deleteTx.id, cascade })}
      />
    </>
  );
}
