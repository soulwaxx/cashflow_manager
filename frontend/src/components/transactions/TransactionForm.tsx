import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { addMonths, format } from 'date-fns';
import { transactionsApi } from '../../api/transactions';
import { paymentMethodsApi } from '../../api/paymentMethods';
import { categoriesApi } from '../../api/categories';
import { queryKeys, invalidateFor } from '../../api/queryKeys';
import { Input } from '../ui/Input';
import { Select } from '../ui/Select';
import { Button } from '../ui/Button';
import type { Transaction, PaymentMethod } from '../../types/api';
import { directionsForPaymentMethod } from '../../utils/transactionSemantics';

const NEXT_MONTH_TYPES: PaymentMethod['type'][] = ['credit_card', 'revolving'];

interface Fields {
  date: string;
  detail: string;
  amount: string;
  payment_method_id: string;
  category_id: string;
  transaction_direction: Transaction['transaction_direction'];
  recurrence_months: string;
  notes: string;
}

interface Props {
  onSuccess: () => void;
  initial?: Transaction;
}

export default function TransactionForm({ onSuccess, initial }: Props) {
  const qc = useQueryClient();
  const isEditing = !!initial;
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [editCascade, setEditCascade] = useState<'single' | 'all' | 'future'>('single');

  type RecurType = 'none' | 'recurring';
  const initRecurType = (): RecurType => {
    if (initial?.recurrence_months) return 'recurring';
    return 'none';
  };
  const [recurType, setRecurType] = useState<RecurType>(initRecurType);

  // Category cascading state
  const [selectedType, setSelectedType] = useState<string>('');

  const { register, watch, handleSubmit, formState: { errors }, setValue } = useForm<Fields>({
    defaultValues: initial
      ? {
          date: initial.date,
          detail: initial.detail,
          amount: String(initial.amount),
          payment_method_id: initial.payment_method_id ?? '',
          category_id: initial.category_id ?? '',
          transaction_direction: initial.transaction_direction,
          recurrence_months: String(initial.recurrence_months ?? ''),
          notes: initial.notes ?? '',
        }
      : {
          transaction_direction: 'debit',
          date: format(new Date(), 'yyyy-MM-dd'),
          detail: '',
          amount: '',
          payment_method_id: '',
          category_id: '',
          recurrence_months: '',
          notes: '',
        },
  });

  const { data: methods = [] } = useQuery({ queryKey: queryKeys.paymentMethods.list('active'), queryFn: () => paymentMethodsApi.list() });
  const { data: categories = [] } = useQuery({ queryKey: queryKeys.categories.list('active'), queryFn: () => categoriesApi.list() });

  const selectedMethodId = watch('payment_method_id');
  const selectedMethod = methods.find((m) => m.id === selectedMethodId);
  const isNextMonth = selectedMethod && NEXT_MONTH_TYPES.includes(selectedMethod.type);
  const availableDirections = directionsForPaymentMethod(selectedMethod?.type);
  const directionIsFixed = availableDirections.length === 1;

  // Reset direction when payment method type changes to avoid submitting an invalid direction
  useEffect(() => {
    if (!selectedMethod) return;
    const available = directionsForPaymentMethod(selectedMethod.type);
    const current = watch('transaction_direction');
    if (available.length === 1) {
      setValue('transaction_direction', available[0].direction);
    } else if (!available.find((d) => d.direction === current)) {
      setValue('transaction_direction', available[0].direction);
    }
  }, [selectedMethod?.type]); // eslint-disable-line react-hooks/exhaustive-deps

  // Billing month hint
  const dateVal = watch('date');
  let billingHint = '';
  if (isNextMonth && dateVal) {
    const d = new Date(dateVal + 'T00:00:00');
    billingHint = `Billed in: ${format(addMonths(d, 1), 'MMMM yyyy')}`;
  } else if (dateVal) {
    billingHint = `Billed in: ${format(new Date(dateVal + 'T00:00:00'), 'MMMM yyyy')}`;
  }

  // Initialise selectedType from existing transaction in edit mode once categories load
  useEffect(() => {
    if (initial?.category_id && categories.length > 0 && !selectedType) {
      const existing = categories.find((c) => c.id === initial.category_id);
      if (existing) setSelectedType(existing.type);
    }
  }, [categories]); // eslint-disable-line react-hooks/exhaustive-deps

  // Derived category options
  const categoryTypes = [...new Set(categories.map((c) => c.type))].sort();
  const subTypeOptions = categories
    .filter((c) => c.type === selectedType)
    .map((c) => ({ value: c.id, label: c.sub_type }));

  function handleRecurTypeChange(next: RecurType) {
    setRecurType(next);
    if (next === 'none') setValue('recurrence_months', '');
  }

  const { mutate, isPending } = useMutation({
    mutationFn: (data: Fields) => {
      if (isEditing) {
        return transactionsApi.update(
          initial.id,
          {
            date: data.date,
            detail: data.detail,
            amount: parseFloat(data.amount),
            category_id: data.category_id || undefined,
            notes: data.notes || null,
          },
          initial.recurrence_months ? editCascade : undefined,
        );
      }
      return transactionsApi.create({
        date: data.date,
        detail: data.detail,
        amount: parseFloat(data.amount),
        payment_method_id: data.payment_method_id,
        category_id: data.category_id,
        transaction_direction: data.transaction_direction,
        ...(data.recurrence_months ? { recurrence_months: parseInt(data.recurrence_months) } : {}),
        ...(data.notes ? { notes: data.notes } : {}),
      });
    },
    onSuccess: () => {
      setSubmitError(null);
      invalidateFor(qc, 'transaction');
      onSuccess();
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
      setSubmitError(
        typeof detail === 'string'
          ? detail
          : Array.isArray(detail)
          ? detail.map((d: any) => d.msg).join('; ')
          : 'Failed to save. Please check your inputs and try again.'
      );
    },
  });

  const methodOptions = methods.map((m) => ({ value: m.id, label: `${m.name} (${m.type})` }));

  // Radio button style helpers
  const radioBase = 'px-3 py-1.5 text-sm rounded border cursor-pointer transition-colors';
  const radioActive = 'bg-blue-600 text-white border-blue-600';
  const radioInactive = 'bg-elevated text-primary border-line-strong hover:border-blue-400';

  return (
    <form onSubmit={handleSubmit((data: Fields) => mutate(data))} className="flex flex-col gap-3">
      <Input
        label="Date" type="date" required
        hint="The actual date of the transaction."
        {...register('date', { required: true })} error={errors.date?.message}
      />
      <Input
        label="Detail" type="text" required
        hint="A short description, e.g. 'Supermarket', 'Netflix subscription'."
        {...register('detail', { required: true })} error={errors.detail?.message}
      />
      <Input
        label="Amount (€)" type="number" step="0.01" required
        hint="The total amount of this transaction in euros."
        {...register('amount', { required: true })}
      />
      {!isEditing ? (
        <Select
          label="Payment method" options={methodOptions} required
          hint={billingHint || 'Which account or card was used.'}
          {...register('payment_method_id', { required: true })}
        />
      ) : (
        <p className="text-xs text-faint">
          Payment method and direction are fixed after creation.
        </p>
      )}

      {/* Two-step category selector */}
      <div className="flex flex-col gap-1">
        <label className="text-sm font-medium text-secondary">
          Category<span className="text-red-500 ml-0.5">*</span>
        </label>
        <select
          className="border rounded px-3 py-2 text-sm bg-elevated text-primary focus:outline-none focus:ring-2 focus:ring-blue-500 border-line-strong"
          value={selectedType}
          onChange={(e) => {
            setSelectedType(e.target.value);
            setValue('category_id', '');
          }}
        >
          <option value="">— select category —</option>
          {categoryTypes.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        {selectedType && (
          <select
            className="border rounded px-3 py-2 text-sm bg-elevated text-primary focus:outline-none focus:ring-2 focus:ring-blue-500 border-line-strong"
            {...register('category_id', { required: true })}
          >
            <option value="">— select sub-category —</option>
            {subTypeOptions.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        )}
        {errors.category_id && <p className="text-xs text-red-600">Category is required</p>}
        <p className="text-xs text-faint">The spending category for budgeting and analytics.</p>
      </div>

      {!isEditing && !directionIsFixed && (
        <Select
          label="Direction"
          hint="Purchase and card payment reduce cash; a debit-card refund restores it."
          options={availableDirections.map(({ direction, label }) => ({ value: direction, label }))}
          required
          {...register('transaction_direction')}
        />
      )}

      {!isEditing ? (
        <div className="flex flex-col gap-1">
          <span className="text-sm font-medium text-secondary">Recurrence</span>
          <div className="flex flex-wrap gap-2 items-center">
            <button
              type="button"
              className={`${radioBase} ${recurType === 'none' ? radioActive : radioInactive}`}
              onClick={() => handleRecurTypeChange('none')}
            >
              None
            </button>
            <button
              type="button"
              className={`${radioBase} ${recurType === 'recurring' ? radioActive : radioInactive}`}
              onClick={() => handleRecurTypeChange('recurring')}
            >
              Recurring every
            </button>
            {recurType === 'recurring' && (
              <input
                type="number"
                min="1"
                placeholder="months"
                className="border rounded px-2 py-1.5 text-sm bg-elevated text-primary focus:outline-none focus:ring-2 focus:ring-blue-500 border-line-strong w-24"
                {...register('recurrence_months')}
              />
            )}
            {recurType === 'recurring' && (
              <span className="text-sm text-secondary">months</span>
            )}
          </div>
          <p className="text-xs text-faint">
            {recurType === 'recurring' && 'Creates a copy of this transaction for each of the next N months.'}
            {recurType === 'none' && 'One-off transaction with no repetition.'}
          </p>
          {recurType !== 'recurring' && <input type="hidden" {...register('recurrence_months')} />}
        </div>
      ) : (
        <p className="text-xs text-faint">
          Recurrence settings cannot be changed from this form.
        </p>
      )}

      <Input label="Notes" type="text" hint="Optional free-text notes for this transaction." {...register('notes')} />
      {initial?.recurrence_months && (
        <Select
          label="Apply changes to"
          hint="Choose how this edit affects recurring occurrences."
          options={[
            { value: 'single', label: 'Only this occurrence' },
            { value: 'future', label: 'This and future occurrences' },
            { value: 'all', label: 'All occurrences' },
          ]}
          value={editCascade}
          onChange={(e) => setEditCascade(e.target.value as 'single' | 'all' | 'future')}
        />
      )}
      {submitError && (
        <p className="text-xs text-red-600 bg-red-50 dark:bg-red-900/20 rounded px-3 py-2">{submitError}</p>
      )}
      <Button type="submit" isLoading={isPending}>
        {initial ? 'Save changes' : 'Add transaction'}
      </Button>
    </form>
  );
}
