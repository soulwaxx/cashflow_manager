import { useState, useEffect, useRef } from 'react';
import { useForm } from 'react-hook-form';
import { useMutation, useQueryClient, useQuery } from '@tanstack/react-query';
import { format } from 'date-fns';
import { transfersApi } from '../../api/transfers';
import { paymentMethodsApi } from '../../api/paymentMethods';
import { accountsApi } from '../../api/accounts';
import { Input } from '../ui/Input';
import { Select } from '../ui/Select';
import { Button } from '../ui/Button';
import type { Transfer } from '../../types/api';

type AccountType = Transfer['from_account_type'];
const ACCOUNT_TYPES: Array<{ value: string; label: string }> = [
  { value: 'bank', label: 'Bank account' },
  { value: 'saving', label: 'Saving account' },
  { value: 'investment', label: 'Investment account' },
  { value: 'pension', label: 'Pension fund' },
];

interface Fields {
  date: string; detail: string; amount: string;
  from_account_type: AccountType; from_account_id: string;
  to_account_type: AccountType; to_account_id: string;
  recurrence_months: string; notes: string;
}

interface Props { onSuccess: () => void; initial?: Transfer; }

export default function TransferForm({ onSuccess, initial }: Props) {
  const qc = useQueryClient();
  const isEditing = !!initial;
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [editCascade, setEditCascade] = useState<'single' | 'future' | 'all'>('single');
  const { register, handleSubmit, watch, setValue } = useForm<Fields>({
    defaultValues: initial
      ? {
          date: initial.date, detail: initial.detail, amount: String(initial.amount),
          from_account_type: initial.from_account_type,
          from_account_id: initial.from_account_id ?? initial.from_payment_method_id ?? '',
          to_account_type: initial.to_account_type,
          to_account_id: initial.to_account_id ?? initial.to_payment_method_id ?? '',
          recurrence_months: String(initial.recurrence_months ?? ''), notes: initial.notes ?? '',
        }
      : { date: format(new Date(), 'yyyy-MM-dd'), from_account_type: 'bank', to_account_type: 'saving' },
  });

  const { data: paymentMethods = [] } = useQuery({
    queryKey: ['payment-methods', 'active'],
    queryFn: () => paymentMethodsApi.list(),
  });
  const { data: accounts = [] } = useQuery({
    queryKey: ['accounts'],
    queryFn: () => accountsApi.list(),
  });

  const fromType = watch('from_account_type');
  const toType = watch('to_account_type');
  const affectsBank = fromType === 'bank' || toType === 'bank';

  const fromMounted = useRef(false);
  const toMounted = useRef(false);
  useEffect(() => {
    if (!fromMounted.current) { fromMounted.current = true; return; }
    setValue('from_account_id', ''); // eslint-disable-line react-hooks/exhaustive-deps
  }, [fromType]);
  useEffect(() => {
    if (!toMounted.current) { toMounted.current = true; return; }
    setValue('to_account_id', ''); // eslint-disable-line react-hooks/exhaustive-deps
  }, [toType]);

  const accountNameOptions = (type: string): { value: string; label: string }[] => {
    if (type === 'bank') {
      const banks = paymentMethods.filter((m) => m.type === 'bank');
      if (banks.length === 0) return [{ value: '', label: '— no bank accounts —' }];
      return banks.map((b) => ({ value: b.id, label: b.name }));
    }
    const options = accounts
      .filter((account) => account.type === type)
      .map((account) => ({ value: account.id, label: account.name }));
    if (options.length === 0) return [{ value: '', label: `— no ${type} accounts —` }];
    return options;
  };

  const { mutate, isPending } = useMutation({
    mutationFn: (d: Fields) => {
      if (isEditing) {
        return transfersApi.update(initial.id, {
          date: d.date,
          detail: d.detail,
          amount: parseFloat(d.amount),
          notes: d.notes || null,
        }, initial.recurrence_months ? editCascade : undefined);
      }
      return transfersApi.create({
        date: d.date, detail: d.detail, amount: parseFloat(d.amount),
        from_account_type: d.from_account_type, from_account_id: d.from_account_id,
        to_account_type: d.to_account_type, to_account_id: d.to_account_id,
        ...(d.recurrence_months ? { recurrence_months: parseInt(d.recurrence_months) } : {}),
        ...(d.notes ? { notes: d.notes } : {}),
      });
    },
    onSuccess: () => {
      setSubmitError(null);
      qc.invalidateQueries({ queryKey: ['transfers'] });
      qc.invalidateQueries({ queryKey: ['summary'] });
      qc.invalidateQueries({ queryKey: ['assets'] });
      qc.invalidateQueries({ queryKey: ['analytics'] });
      onSuccess();
    },
    onError: (err: unknown) => {
      const axiosErr = err as { response?: { data?: { detail?: unknown } } };
      const detail = axiosErr?.response?.data?.detail;
      setSubmitError(
        typeof detail === 'string'
          ? detail
          : Array.isArray(detail)
          ? detail.map((d: { msg?: string }) => d.msg ?? String(d)).join('; ')
          : 'Failed to save. Please check your inputs and try again.'
      );
    },
  });

  return (
    <form onSubmit={handleSubmit((d) => mutate(d))} className="flex flex-col gap-3">
      <Input label="Date" type="date" required {...register('date', { required: true })} />
      <Input label="Detail" type="text" required {...register('detail', { required: true })} />
      <Input label="Amount (€)" type="number" step="0.01" required {...register('amount', { required: true })} />
      <p className={`text-xs ${affectsBank ? 'text-blue-600 dark:text-blue-400' : 'text-faint'}`}>
        {affectsBank
          ? 'This transfer will affect your bank balance.'
          : 'This transfer does not affect your bank balance.'}
      </p>
      {!isEditing ? (
        <>
          <Select label="From account type" options={ACCOUNT_TYPES} {...register('from_account_type')} />
          <Select
            label="From account"
            options={accountNameOptions(fromType)}
            required
            {...register('from_account_id', { required: true })}
          />
          <Select label="To account type" options={ACCOUNT_TYPES} {...register('to_account_type')} />
          <Select
            label="To account"
            options={accountNameOptions(toType)}
            required
            {...register('to_account_id', { required: true })}
          />
          <Input label="Repeat for N months" type="number" min="1" {...register('recurrence_months')} />
        </>
      ) : (
        <p className="text-xs text-faint">
          Account endpoints and recurrence settings cannot be changed from this form.
        </p>
      )}
      <Input label="Notes" type="text" {...register('notes')} />
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
          onChange={(e) => setEditCascade(e.target.value as 'single' | 'future' | 'all')}
        />
      )}
      {submitError && (
        <p className="text-xs text-red-600 bg-red-50 dark:bg-red-900/20 rounded px-3 py-2">{submitError}</p>
      )}
      <Button type="submit" isLoading={isPending}>{initial ? 'Save changes' : 'Add transfer'}</Button>
    </form>
  );
}
