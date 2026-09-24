import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { forecastsApi } from '../../api/forecasts';
import { invalidateForecast } from '../../api/queryKeys';
import type { ForecastLineAdjustment } from '../../types/api';
import Modal from '../ui/Modal';
import { Input } from '../ui/Input';
import { Button } from '../ui/Button';
import { forecastError } from './forecastErrors';

interface Props {
  open: boolean;
  onClose: () => void;
  forecastId: string;
  lineId: string;
  adjustment?: ForecastLineAdjustment;
  startMonth?: string;
  endMonth?: string;
}

interface Fields {
  valid_from: string;
  new_amount: string;
  adjustment_type: 'fixed' | 'percentage';
}

export default function AdjustmentModal({ open, onClose, forecastId, lineId, adjustment, startMonth, endMonth }: Props) {
  const qc = useQueryClient();
  const [submitError, setSubmitError] = useState<string | null>(null);
  const { register, handleSubmit, watch, setError, formState: { errors } } = useForm<Fields>({
    defaultValues: {
      valid_from: adjustment?.valid_from.slice(0, 7) ?? '',
      new_amount: adjustment ? String(adjustment.new_amount) : '',
      adjustment_type: adjustment?.adjustment_type ?? 'fixed',
    },
  });
  const adjustmentType = watch('adjustment_type');

  const { mutate, isPending } = useMutation({
    mutationFn: (fields: Fields) => {
      const body = {
        valid_from: `${fields.valid_from}-01`,
        new_amount: Number(fields.new_amount),
        adjustment_type: fields.adjustment_type,
      };
      return adjustment
        ? forecastsApi.updateAdjustment(forecastId, lineId, adjustment.id, body)
        : forecastsApi.addAdjustment(forecastId, lineId, body);
    },
    onSuccess: () => {
      invalidateForecast(qc, forecastId);
      onClose();
    },
    onError: (error: unknown) => {
      const result = forecastError(error);
      setSubmitError(result.message);
      if (result.fields.valid_from) setError('valid_from', { message: result.fields.valid_from });
      if (result.fields.new_amount) setError('new_amount', { message: result.fields.new_amount });
      if (result.fields.adjustment_type) setError('adjustment_type', { message: result.fields.adjustment_type });
    },
  });

  return (
    <Modal open={open} onClose={onClose} title={adjustment ? 'Edit adjustment' : 'Add adjustment'}>
      <form onSubmit={handleSubmit((fields) => { setSubmitError(null); mutate(fields); })} className="flex flex-col gap-3">
        <Input label="Start month (YYYY-MM)" type="month" min={startMonth} max={endMonth} required
          {...register('valid_from', { required: 'Start month is required' })} error={errors.valid_from?.message} />
        <div className="flex flex-col gap-1">
          <label htmlFor="adjustment-type" className="text-sm font-medium text-secondary">Adjustment type</label>
          <select id="adjustment-type" {...register('adjustment_type')}
            className="border border-line-strong rounded px-3 py-2 text-sm bg-elevated text-primary">
            <option value="fixed">Fixed amount (€)</option>
            <option value="percentage">Percentage change (%)</option>
          </select>
          {errors.adjustment_type && <p className="text-xs text-red-600">{errors.adjustment_type.message}</p>}
        </div>
        <Input
          label={adjustmentType === 'percentage' ? 'Percentage change (%)' : 'New amount (€)'}
          type="number" min={adjustmentType === 'percentage' ? '-100' : '0'} step="0.01" required
          {...register('new_amount', { required: 'Amount is required' })} error={errors.new_amount?.message}
        />
        {submitError && <p role="alert" className="text-sm text-red-600">{submitError}</p>}
        <Button type="submit" isLoading={isPending}>{adjustment ? 'Save adjustment' : 'Add adjustment'}</Button>
      </form>
    </Modal>
  );
}
