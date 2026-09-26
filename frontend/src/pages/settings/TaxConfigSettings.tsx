import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { taxConfigApi } from '../../api/taxConfig';
import { queryKeys, invalidateFor } from '../../api/queryKeys';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import Modal from '../../components/ui/Modal';
import type { TaxConfig } from '../../types/api';
import { fmt } from '../../utils/format';

type Fields = Omit<TaxConfig, 'id'>;

export default function TaxConfigSettings() {
  const qc = useQueryClient();
  const [addOpen, setAddOpen] = useState(false);
  const [confirmId, setConfirmId] = useState<string | null>(null);

  const { data: configs = [], isLoading } = useQuery({
    queryKey: queryKeys.taxConfig.all,
    queryFn: taxConfigApi.list,
  });

  const { register, handleSubmit, reset } = useForm<Fields & { valid_from_input: string }>();

  const { mutate: create, isPending } = useMutation({
    mutationFn: (d: Fields & { valid_from_input: string }) =>
      taxConfigApi.create({ ...d, valid_from: `${d.valid_from_input}-01` }),
    onSuccess: () => {
      invalidateFor(qc, 'tax');
      setAddOpen(false);
      reset();
    },
  });

  const { mutate: del } = useMutation({
    mutationFn: (id: string) => taxConfigApi.delete(id),
    onSuccess: () => invalidateFor(qc, 'tax'),
  });

  const earliest = configs[0]?.id;

  if (isLoading) return <div className="animate-pulse h-32 bg-muted-bg rounded" />;

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <Button onClick={() => setAddOpen(true)}>+ Add period</Button>
      </div>
      {configs.map((cfg) => (
        <div key={cfg.id} className="bg-surface border border-line rounded-xl p-4 sm:p-5 text-sm">
          <div className="flex flex-wrap justify-between items-center gap-2 mb-3">
            <span className="font-medium text-primary">From {cfg.valid_from}</span>
            {cfg.id !== earliest ? (
              <Button variant="ghost" className="text-xs text-red-500"
                onClick={() => setConfirmId(cfg.id)}>
                Delete
              </Button>
            ) : (
              <span className="text-xs text-faint">earliest — read-only</span>
            )}
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs text-secondary">
            <span>INPS rate: {(cfg.inps_rate * 100).toFixed(2)}%</span>
            <span>Band 1: {(cfg.irpef_band1_rate * 100).toFixed(0)}% up to €{fmt(cfg.irpef_band1_limit)}</span>
            <span>Band 2: {(cfg.irpef_band2_rate * 100).toFixed(0)}% up to €{fmt(cfg.irpef_band2_limit)}</span>
            <span>Band 3: {(cfg.irpef_band3_rate * 100).toFixed(0)}% above</span>
            <span>Pension cap: €{fmt(cfg.pension_deductibility_cap)}</span>
            <span>Deduction floor: €{fmt(cfg.employment_deduction_floor)}</span>
          </div>
          <details className="mt-2">
            <summary className="text-xs text-faint cursor-pointer">Employment deduction details</summary>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs text-muted mt-2">
              <span>Band 1 limit: €{fmt(cfg.employment_deduction_band1_limit)}</span>
              <span>Band 1 amount: €{fmt(cfg.employment_deduction_band1_amount)}</span>
              <span>Band 2 upper: €{fmt(cfg.employment_deduction_band2_limit)}</span>
              <span>Band 2 base: €{fmt(cfg.employment_deduction_band2_base)}</span>
              <span>Band 2 variable: €{fmt(cfg.employment_deduction_band2_variable)}</span>
              <span>Band 2 range: €{fmt(cfg.employment_deduction_band2_range)}</span>
              <span>Band 3 upper: €{fmt(cfg.employment_deduction_band3_limit)}</span>
              <span>Band 3 base: €{fmt(cfg.employment_deduction_band3_base)}</span>
              <span>Band 3 range: €{fmt(cfg.employment_deduction_band3_range)}</span>
            </div>
          </details>
        </div>
      ))}

      <Modal open={!!confirmId} onClose={() => setConfirmId(null)} title="Delete tax config period">
        <p className="text-sm text-secondary mb-4">Are you sure you want to delete this tax config period? This cannot be undone.</p>
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setConfirmId(null)}>Cancel</Button>
          <Button variant="ghost" className="text-red-500" onClick={() => { del(confirmId!); setConfirmId(null); }}>Confirm Delete</Button>
        </div>
      </Modal>

      <Modal open={addOpen} onClose={() => setAddOpen(false)} title="Add tax config period">
        <form onSubmit={handleSubmit((d) => create(d))} className="flex flex-col gap-3">
          <Input label="Valid from (YYYY-MM)" type="month" {...register('valid_from_input', { required: true })} />
          <Input label="INPS rate" type="number" step="0.0001" defaultValue="0.0919" {...register('inps_rate', { required: true, valueAsNumber: true })} />
          <Input label="Band 1 rate" type="number" step="0.01" defaultValue="0.23" {...register('irpef_band1_rate', { required: true, valueAsNumber: true })} />
          <Input label="Band 1 limit (€)" type="number" step="100" defaultValue="28000" {...register('irpef_band1_limit', { required: true, valueAsNumber: true })} />
          <Input label="Band 2 rate" type="number" step="0.01" defaultValue="0.33" {...register('irpef_band2_rate', { required: true, valueAsNumber: true })} />
          <Input label="Band 2 limit (€)" type="number" step="100" defaultValue="50000" {...register('irpef_band2_limit', { required: true, valueAsNumber: true })} />
          <Input label="Band 3 rate" type="number" step="0.01" defaultValue="0.43" {...register('irpef_band3_rate', { required: true, valueAsNumber: true })} />
          <Input label="Pension deductibility cap (€)" type="number" step="0.01" defaultValue="5300" {...register('pension_deductibility_cap', { required: true, valueAsNumber: true })} />
          <p className="text-xs font-medium text-secondary mt-1">Employment deduction</p>
          <Input label="Band 1 limit (€)" type="number" step="100" defaultValue="15000" {...register('employment_deduction_band1_limit', { required: true, valueAsNumber: true })} />
          <Input label="Band 1 amount (€)" type="number" step="1" defaultValue="1955" {...register('employment_deduction_band1_amount', { required: true, valueAsNumber: true })} />
          <Input label="Band 2 upper limit (€)" type="number" step="100" defaultValue="28000" {...register('employment_deduction_band2_limit', { required: true, valueAsNumber: true })} />
          <Input label="Band 2 base (€)" type="number" step="1" defaultValue="1910" {...register('employment_deduction_band2_base', { required: true, valueAsNumber: true })} />
          <Input label="Band 2 variable (€)" type="number" step="1" defaultValue="1190" {...register('employment_deduction_band2_variable', { required: true, valueAsNumber: true })} />
          <Input label="Band 2 range (€)" type="number" step="100" defaultValue="13000" {...register('employment_deduction_band2_range', { required: true, valueAsNumber: true })} />
          <Input label="Band 3 upper limit (€)" type="number" step="100" defaultValue="50000" {...register('employment_deduction_band3_limit', { required: true, valueAsNumber: true })} />
          <Input label="Band 3 base (€)" type="number" step="1" defaultValue="1910" {...register('employment_deduction_band3_base', { required: true, valueAsNumber: true })} />
          <Input label="Band 3 range (€)" type="number" step="100" defaultValue="22000" {...register('employment_deduction_band3_range', { required: true, valueAsNumber: true })} />
          <Input label="Minimum floor (€)" type="number" step="1" defaultValue="690" {...register('employment_deduction_floor', { required: true, valueAsNumber: true })} />
          <Button type="submit" isLoading={isPending}>Add period</Button>
        </form>
      </Modal>
    </div>
  );
}
