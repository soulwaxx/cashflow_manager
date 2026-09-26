import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { categoriesApi } from '../../api/categories';
import { queryKeys, invalidateFor } from '../../api/queryKeys';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import Modal from '../../components/ui/Modal';
import { Badge } from '../../components/ui/Badge';
import type { Category } from '../../types/api';

interface AddFields { type: string; sub_type: string; }
interface EditFields { type: string; sub_type: string; }

export default function CategoriesSettings() {
  const qc = useQueryClient();
  const [addOpen, setAddOpen] = useState(false);
  const [editCat, setEditCat] = useState<Category | null>(null);

  const { data: categories = [], isLoading } = useQuery({
    queryKey: queryKeys.categories.list('all'),
    queryFn: () => categoriesApi.list(false),
  });

  const { register: registerAdd, handleSubmit: handleAdd, reset: resetAdd } = useForm<AddFields>();
  const { register: registerEdit, handleSubmit: handleEdit, reset: resetEdit } = useForm<EditFields>();

  const { mutate: create, isPending: creating } = useMutation({
    mutationFn: (d: AddFields) => categoriesApi.create(d),
    onSuccess: () => {
      invalidateFor(qc, 'category');
      setAddOpen(false);
      resetAdd();
    },
  });

  const { mutate: update, isPending: updating } = useMutation({
    mutationFn: (d: EditFields) => categoriesApi.update(editCat!.id, d),
    onSuccess: () => {
      invalidateFor(qc, 'category');
      setEditCat(null);
    },
  });

  const { mutate: deactivate } = useMutation({
    mutationFn: (id: string) => categoriesApi.update(id, { is_active: false }),
    onSuccess: () => invalidateFor(qc, 'category'),
  });

  const { mutate: reactivate } = useMutation({
    mutationFn: (id: string) => categoriesApi.update(id, { is_active: true }),
    onSuccess: () => invalidateFor(qc, 'category'),
  });

  if (isLoading) return <div className="animate-pulse h-32 bg-muted-bg rounded" />;

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <Button onClick={() => setAddOpen(true)}>+ Add category</Button>
      </div>
      <ul className="space-y-1">
        {categories.map((c) => (
          <li key={c.id} className="bg-surface border border-line rounded-xl p-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between text-sm text-primary">
            <div className="flex flex-wrap items-center gap-2 break-words">
              <span>{c.type}</span>
              <span className="text-faint">/</span>
              <span>{c.sub_type}</span>
              {!c.is_active && <Badge color="gray">Inactive</Badge>}
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="ghost" className="text-xs" onClick={() => { setEditCat(c); resetEdit({ type: c.type, sub_type: c.sub_type }); }}>Rename</Button>
              {c.is_active ? (
                <Button variant="ghost" className="text-xs text-red-500" onClick={() => window.confirm(`Deactivate ${c.type}/${c.sub_type}? Existing transactions will remain.`) && deactivate(c.id)}>Deactivate</Button>
              ) : (
                <Button variant="ghost" className="text-xs" onClick={() => reactivate(c.id)}>Reactivate</Button>
              )}
            </div>
          </li>
        ))}
      </ul>

      <Modal open={addOpen} onClose={() => setAddOpen(false)} title="Add category">
        <form onSubmit={handleAdd((d) => create(d))} className="flex flex-col gap-3">
          <Input label="Type" type="text" {...registerAdd('type', { required: true })} />
          <Input label="Sub-type" type="text" {...registerAdd('sub_type', { required: true })} />
          <Button type="submit" isLoading={creating}>Add</Button>
        </form>
      </Modal>

      <Modal open={!!editCat} onClose={() => setEditCat(null)} title="Rename category">
        <form onSubmit={handleEdit((d) => update(d))} className="flex flex-col gap-3">
          <Input label="Type" type="text" {...registerEdit('type', { required: true })} />
          <Input label="Sub-type" type="text" {...registerEdit('sub_type', { required: true })} />
          <p className="text-xs text-muted">Renaming updates the display name across all historical and future transactions immediately.</p>
          <Button type="submit" isLoading={updating}>Save</Button>
        </form>
      </Modal>
    </div>
  );
}
