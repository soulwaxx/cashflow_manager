import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { forecastsApi } from '../../api/forecasts';
import { queryKeys } from '../../api/queryKeys';
import { Input } from '../ui/Input';
import { Button } from '../ui/Button';
import { forecastError } from './forecastErrors';

interface Fields { name: string; base_year: string; projection_years: string; }
interface Props { onSuccess: () => void; }

export default function CreateForecastForm({ onSuccess }: Props) {
  const qc = useQueryClient();
  const [submitError, setSubmitError] = useState<string | null>(null);
  const { register, handleSubmit, setError, formState: { errors } } = useForm<Fields>({
    defaultValues: { base_year: String(new Date().getFullYear()), projection_years: '3' },
  });

  const { mutate, isPending } = useMutation({
    mutationFn: (d: Fields) =>
      forecastsApi.create({
        name: d.name,
        base_year: parseInt(d.base_year),
        projection_years: parseInt(d.projection_years),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.forecasts.all });
      onSuccess();
    },
    onError: (error: unknown) => {
      const result = forecastError(error);
      setSubmitError(result.message);
      if (result.fields.name) setError('name', { message: result.fields.name });
      if (result.fields.base_year) setError('base_year', { message: result.fields.base_year });
      if (result.fields.projection_years) setError('projection_years', { message: result.fields.projection_years });
    },
  });

  return (
    <form onSubmit={handleSubmit((d) => { setSubmitError(null); mutate(d); })} className="flex flex-col gap-3">
      <Input label="Forecast name" type="text" required {...register('name', { required: 'Name is required' })} error={errors.name?.message} />
      <Input label="Base year" type="number" min="2000" max="2100" required {...register('base_year', { required: 'Base year is required' })} error={errors.base_year?.message} />
      <Input label="Projection years (1–10)" type="number" min="1" max="10" required {...register('projection_years', { required: 'Projection years are required' })} error={errors.projection_years?.message} />
      <p className="text-xs text-gray-500">
        Recurring debit purchases still occurring in December of the base year will be imported as editable monthly commitments.
      </p>
      {submitError && <p role="alert" className="text-sm text-red-600">{submitError}</p>}
      <Button type="submit" isLoading={isPending}>Create forecast</Button>
    </form>
  );
}
