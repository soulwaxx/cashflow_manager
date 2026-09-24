import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { categoriesApi } from '../../api/categories';
import { paymentMethodsApi } from '../../api/paymentMethods';
import { forecastsApi } from '../../api/forecasts';
import { queryKeys, invalidateForecast } from '../../api/queryKeys';
import type { ForecastLine, ForecastLineRequest } from '../../types/api';
import Modal from '../ui/Modal';
import { Input } from '../ui/Input';
import { Button } from '../ui/Button';
import { forecastError } from './forecastErrors';

interface Props {
  onClose: () => void;
  forecastId: string;
  line?: ForecastLine;
}

interface Fields {
  detail: string;
  base_amount: string;
  category_id: string;
  payment_method_id: string;
  billing_day: string;
  notes: string;
}

export default function LineModal({ onClose, forecastId, line }: Props) {
  const qc = useQueryClient();
  const [submitError, setSubmitError] = useState<string | null>(null);
  const { data: categories = [], isLoading: categoriesLoading, isError: categoriesError } = useQuery({
    queryKey: queryKeys.categories.list('all'), queryFn: () => categoriesApi.list(false),
  });
  const { data: methods = [], isLoading: methodsLoading, isError: methodsError } = useQuery({
    queryKey: queryKeys.paymentMethods.list('all'), queryFn: () => paymentMethodsApi.list(false),
  });
  const { register, handleSubmit, setError, formState: { errors } } = useForm<Fields>({
    defaultValues: {
      detail: line?.detail ?? '', base_amount: line ? String(line.base_amount) : '',
      category_id: line?.category_id ?? '', payment_method_id: line?.payment_method_id ?? '',
      billing_day: String(line?.billing_day ?? 1), notes: line?.notes ?? '',
    },
  });
  const { mutate, isPending } = useMutation({
    mutationFn: (fields: Fields) => {
      const body: ForecastLineRequest = {
        detail: fields.detail.trim(), base_amount: Number(fields.base_amount),
        category_id: fields.category_id || null, payment_method_id: fields.payment_method_id || null,
        billing_day: Number(fields.billing_day), notes: fields.notes || null,
      };
      return line
        ? forecastsApi.updateLine(forecastId, line.id, body)
        : forecastsApi.addLine(forecastId, body);
    },
    onSuccess: () => {
      invalidateForecast(qc, forecastId);
      onClose();
    },
    onError: (error: unknown) => {
      const result = forecastError(error);
      setSubmitError(result.message);
      for (const [field, message] of Object.entries(result.fields)) {
        if (field in { detail: 1, base_amount: 1, category_id: 1, payment_method_id: 1, billing_day: 1, notes: 1 }) {
          setError(field as keyof Fields, { message });
        }
      }
    },
  });

  return (
    <Modal open onClose={onClose} title={line ? 'Edit commitment' : 'Add commitment'}>
      {categoriesError || methodsError ? (
        <p role="alert" className="text-sm text-red-600">Could not load categories or payment methods. Close and try again.</p>
      ) : categoriesLoading || methodsLoading ? (
        <p className="text-sm text-muted">Loading commitment options…</p>
      ) : (
      <form onSubmit={handleSubmit((fields) => { setSubmitError(null); mutate(fields); })} className="flex flex-col gap-3">
        <Input label="Detail" required {...register('detail', { required: 'Detail is required' })} error={errors.detail?.message} />
        <Input label="Monthly amount (€)" type="number" min="0" step="0.01" required
          {...register('base_amount', { required: 'Amount is required' })} error={errors.base_amount?.message} />
        <div className="flex flex-col gap-1">
          <label htmlFor="forecast-category" className="text-sm font-medium text-secondary">Category</label>
          <select id="forecast-category" {...register('category_id')} className="border border-line-strong rounded px-3 py-2 bg-elevated text-primary">
            <option value="">None</option>
            {line?.category_id && !categories.some((category) => category.id === line.category_id) && (
              <option value={line.category_id}>Unavailable category — choose another</option>
            )}
            {categories.map((category) => <option key={category.id} value={category.id}>{category.type} / {category.sub_type}</option>)}
          </select>
          {errors.category_id && <p className="text-xs text-red-600">{errors.category_id.message}</p>}
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="forecast-method" className="text-sm font-medium text-secondary">Payment method</label>
          <select id="forecast-method" {...register('payment_method_id')} className="border border-line-strong rounded px-3 py-2 bg-elevated text-primary">
            <option value="">None</option>
            {line?.payment_method_id && !methods.some((method) => method.id === line.payment_method_id) && (
              <option value={line.payment_method_id}>Unavailable payment method — choose another</option>
            )}
            {methods.map((method) => <option key={method.id} value={method.id}>{method.name}</option>)}
          </select>
          {errors.payment_method_id && <p className="text-xs text-red-600">{errors.payment_method_id.message}</p>}
        </div>
        <Input label="Day of month (reference only)" type="number" min="1" max="31" required
          {...register('billing_day', { required: 'Day is required' })} error={errors.billing_day?.message} />
        <Input label="Notes" {...register('notes')} error={errors.notes?.message} />
        {submitError && <p role="alert" className="text-sm text-red-600">{submitError}</p>}
        <Button type="submit" isLoading={isPending}>{line ? 'Save commitment' : 'Add commitment'}</Button>
      </form>
      )}
    </Modal>
  );
}
