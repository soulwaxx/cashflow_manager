import { useState } from 'react';
import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { transfersApi } from '../../api/transfers';
import { queryKeys, invalidateFor } from '../../api/queryKeys';
import { fmt } from '../../utils/format';
import TransferForm from './TransferForm';
import CascadeDeleteModal from './CascadeDeleteModal';
import Modal from '../ui/Modal';
import { Button } from '../ui/Button';
import { Badge } from '../ui/Badge';
import type { Transfer } from '../../types/api';

const PAGE_SIZE = 100;

export default function TransferList() {
  const qc = useQueryClient();
  const [addOpen, setAddOpen] = useState(false);
  const [editTr, setEditTr] = useState<Transfer | null>(null);
  const [deleteTr, setDeleteTr] = useState<Transfer | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const {
    data,
    isLoading,
    isFetchingNextPage,
    hasNextPage,
    fetchNextPage,
  } = useInfiniteQuery({
    queryKey: queryKeys.transfers.paged,
    initialPageParam: 0,
    queryFn: ({ pageParam }) => transfersApi.list({ limit: PAGE_SIZE, offset: pageParam }),
    getNextPageParam: (lastPage, _pages, lastPageParam) =>
      lastPage.length === PAGE_SIZE ? lastPageParam + PAGE_SIZE : undefined,
  });
  const transfers = data?.pages.flatMap((page) => page) ?? [];

  const { mutate: deleteOne, isPending: deleteLoading } = useMutation({
    mutationFn: ({ id, cascade }: { id: string; cascade: string }) =>
      transfersApi.delete(id, cascade),
    onSuccess: () => {
      setDeleteError(null);
      invalidateFor(qc, 'transfer');
      setDeleteTr(null);
    },
    onError: (err: unknown) => {
      const axiosErr = err as { response?: { data?: { detail?: unknown } } };
      const detail = axiosErr?.response?.data?.detail;
      setDeleteError(
        typeof detail === 'string'
          ? detail
          : Array.isArray(detail)
          ? detail.map((d: { msg?: string }) => d.msg ?? String(d)).join('; ')
          : 'Failed to delete transfer. Please retry.'
      );
    },
  });

  if (isLoading) return <div className="animate-pulse h-32 bg-muted-bg rounded" />;

  return (
    <>
      <div className="flex justify-between items-center mb-3">
        <h2 className="font-semibold text-secondary">Transfers</h2>
        <Button onClick={() => setAddOpen(true)}>+ Add transfer</Button>
      </div>
      {deleteError && (
        <p className="mb-3 text-xs text-red-600 bg-red-50 dark:bg-red-900/20 rounded px-3 py-2">
          {deleteError}
        </p>
      )}
      <ul className="bg-surface rounded-lg border border-line divide-y divide-line text-sm">
        {transfers.length === 0 && <li className="p-4 text-faint">No transfers</li>}
        {transfers.map((tr) => (
          <li key={tr.id} className="p-3 flex items-center gap-3">
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <span className="font-medium text-primary">{tr.detail}</span>
                {tr.recurrence_months && <span title="Recurring" className="text-blue-400 text-xs">↻</span>}
              </div>
              <div className="text-muted text-xs mt-0.5">
                {tr.date} · <span>{tr.from_account_name}</span> → <span>{tr.to_account_name}</span>
              </div>
            </div>
            <Badge color="blue">€{fmt(tr.amount)}</Badge>
            <div className="flex gap-1">
              <Button variant="ghost" className="text-xs px-2" onClick={() => setEditTr(tr)}>Edit</Button>
              <Button
                variant="ghost"
                className="text-xs px-2 text-red-500"
                onClick={() => {
                  setDeleteError(null);
                  setDeleteTr(tr);
                }}
              >
                Delete
              </Button>
            </div>
          </li>
        ))}
      </ul>
      {hasNextPage && (
        <div className="flex justify-center mt-3">
          <Button variant="secondary" onClick={() => fetchNextPage()} isLoading={isFetchingNextPage}>
            Load more
          </Button>
        </div>
      )}

      <Modal open={addOpen} onClose={() => setAddOpen(false)} title="Add transfer">
        <TransferForm onSuccess={() => setAddOpen(false)} />
      </Modal>
      <Modal open={!!editTr} onClose={() => setEditTr(null)} title="Edit transfer">
        {editTr && <TransferForm initial={editTr} onSuccess={() => setEditTr(null)} />}
      </Modal>
      <CascadeDeleteModal
        open={!!deleteTr}
        onClose={() => setDeleteTr(null)}
        isRecurring={!!deleteTr?.recurrence_months}
        isPending={deleteLoading}
        onConfirm={(cascade) => deleteTr && deleteOne({ id: deleteTr.id, cascade })}
      />
    </>
  );
}
