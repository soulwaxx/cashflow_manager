import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { paymentMethodsApi } from '../../api/paymentMethods';
import { Button } from '../../components/ui/Button';
import Modal from '../../components/ui/Modal';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { Badge } from '../../components/ui/Badge';
import type { PaymentMethod } from '../../types/api';

type CreateFormValues = {
  name: string;
  type: PaymentMethod['type'] | '';
  opening_balance: string;
  linked_bank_id: string;
  has_stamp_duty: boolean;
};

const TYPE_OPTIONS: { value: PaymentMethod['type']; label: string }[] = [
  { value: 'bank', label: 'Bank' },
  { value: 'debit_card', label: 'Debit card' },
  { value: 'credit_card', label: 'Credit card' },
  { value: 'revolving', label: 'Revolving' },
  { value: 'prepaid', label: 'Prepaid' },
  { value: 'cash', label: 'Cash' },
];

const LINKABLE_TYPES: PaymentMethod['type'][] = ['debit_card', 'credit_card', 'revolving'];

export default function PaymentMethodsSettings() {
  const qc = useQueryClient();
  const [switchBankId, setSwitchBankId] = useState<string | null>(null);
  const [newBalance, setNewBalance] = useState('');
  const [addOpen, setAddOpen] = useState(false);
  const [editMethod, setEditMethod] = useState<PaymentMethod | null>(null);
  const [editName, setEditName] = useState('');
  const [editLinkedBankId, setEditLinkedBankId] = useState('');
  const [editEffectiveBillingMonth, setEditEffectiveBillingMonth] = useState('');
  const [editHasStampDuty, setEditHasStampDuty] = useState(false);

  const { data: methods = [], isLoading } = useQuery({
    queryKey: ['payment-methods', 'all'],
    queryFn: () => paymentMethodsApi.list(false),
  });

  const { mutate: deactivate } = useMutation({
    mutationFn: (id: string) => paymentMethodsApi.update(id, { is_active: false }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['payment-methods'] }),
  });

  const { mutate: reactivate } = useMutation({
    mutationFn: (id: string) => paymentMethodsApi.update(id, { is_active: true }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['payment-methods'] }),
  });

  const { mutate: editMutate, isPending: editing } = useMutation({
    mutationFn: ({ id, name, linked_bank_id, effective_billing_month, has_stamp_duty }: {
      id: string; name: string; linked_bank_id?: string; effective_billing_month?: string; has_stamp_duty?: boolean;
    }) =>
      paymentMethodsApi.update(id, { name, linked_bank_id, effective_billing_month, has_stamp_duty }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['payment-methods'] });
      setEditMethod(null);
    },
  });

  const { mutate: setMain, isPending: settingMain } = useMutation({
    mutationFn: ({ id, balance }: { id: string; balance: number }) =>
      paymentMethodsApi.setMainBank(id, balance),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['payment-methods'] });
      setSwitchBankId(null);
      setNewBalance('');
    },
  });

  const {
    register,
    handleSubmit,
    watch,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<CreateFormValues>({
    defaultValues: { name: '', type: 'debit_card', opening_balance: '', linked_bank_id: '', has_stamp_duty: false },
  });

  const selectedType = watch('type');
  const isBank = selectedType === 'bank';
  const isCreditCard = selectedType === 'credit_card';
  const isLinkable = LINKABLE_TYPES.includes(selectedType as PaymentMethod['type']);
  const bankMethods = methods.filter((m) => m.type === 'bank' && m.is_active);

  const { mutate: createMethod, isPending: creating, error: createMutationError, reset: resetCreateMutation } = useMutation({
    mutationFn: (body: Omit<PaymentMethod, 'id' | 'user_id'>) => paymentMethodsApi.create(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['payment-methods'] });
      setAddOpen(false);
      reset();
    },
  });

  const onSubmit = (values: CreateFormValues) => {
    if (!values.type) return;
    createMethod({
      name: values.name,
      type: values.type as PaymentMethod['type'],
      is_main_bank: false,
      is_active: true,
      linked_bank_id: isLinkable && values.linked_bank_id ? values.linked_bank_id : null,
      opening_balance: isBank ? parseFloat(values.opening_balance) || 0 : null,
      has_stamp_duty: isCreditCard ? values.has_stamp_duty : false,
    });
  };

  const handleAddClose = () => {
    setAddOpen(false);
    resetCreateMutation();
    reset();
  };

  if (isLoading) return <div className="animate-pulse h-32 bg-muted-bg rounded" />;

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <Button variant="secondary" onClick={() => setAddOpen(true)}>
          + Add
        </Button>
      </div>

      <ul className="space-y-2">
        {methods.map((m) => (
          <li key={m.id} className="bg-surface border border-line rounded-lg p-4 flex items-center justify-between">
            <div>
              <div className="flex items-center gap-2">
                <span className="font-medium text-primary">{m.name}</span>
                {m.is_main_bank && <Badge color="blue">Main bank</Badge>}
                {!m.is_active && <Badge color="gray">Inactive</Badge>}
              </div>
              <div className="text-xs text-muted mt-0.5">{m.type}</div>
            </div>
            <div className="flex gap-2">
              <Button
                variant="secondary"
                className="text-xs"
                onClick={() => {
                  setEditMethod(m);
                  setEditName(m.name);
                  setEditLinkedBankId(m.linked_bank_id ?? '');
                  setEditEffectiveBillingMonth('');
                  setEditHasStampDuty(m.has_stamp_duty ?? false);
                }}
              >
                Edit
              </Button>
              {m.type === 'bank' && !m.is_main_bank && m.is_active && (
                <Button variant="secondary" className="text-xs" onClick={() => setSwitchBankId(m.id)}>
                  Set as main bank
                </Button>
              )}
              {m.is_active ? (
                <Button
                  variant="ghost"
                  className="text-xs text-red-500"
                  onClick={() => window.confirm('Deactivate?') && deactivate(m.id)}
                >
                  Deactivate
                </Button>
              ) : (
                <Button
                  variant="secondary"
                  className="text-xs"
                  onClick={() => reactivate(m.id)}
                >
                  Reactivate
                </Button>
              )}
            </div>
          </li>
        ))}
      </ul>

      {/* Add payment method modal */}
      <Modal open={addOpen} onClose={handleAddClose} title="Add payment method">
        <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-3">
          <Input
            label="Name"
            type="text"
            error={errors.name?.message}
            {...register('name', { required: 'Name is required' })}
          />

          <Select
            label="Type"
            options={TYPE_OPTIONS}
            error={errors.type?.message}
            {...register('type', { required: 'Type is required' })}
          />

          {isBank && (
            <Input
              label="Opening balance (€)"
              type="number"
              step="0.01"
              {...register('opening_balance')}
            />
          )}

          {isLinkable && bankMethods.length > 0 && (
            <Select
              label="Linked bank"
              options={bankMethods.map((b) => ({ value: b.id, label: b.name }))}
              required
              error={errors.linked_bank_id?.message}
              {...register('linked_bank_id', { required: 'Linked bank is required for card payment methods' })}
            />
          )}

          {isCreditCard && (
            <label className="flex items-center gap-2 text-sm text-secondary cursor-pointer">
              <input
                type="checkbox"
                className="w-4 h-4"
                {...register('has_stamp_duty')}
              />
              Stamp duty (imposta di bollo)
            </label>
          )}

          {createMutationError && (
            <p className="text-sm text-red-600 dark:text-red-400">Failed to create. Please try again.</p>
          )}

          <Button type="submit" isLoading={creating || isSubmitting}>
            Create
          </Button>
        </form>
      </Modal>

      {/* Set main bank modal */}
      <Modal open={!!switchBankId} onClose={() => setSwitchBankId(null)} title="Set as main bank">
        <div className="flex flex-col gap-3">
          <p className="text-sm text-secondary">
            Enter the current balance of this account. The switch takes effect from the first day of the current month.
          </p>
          <Input
            label="Current balance (€)"
            type="number"
            step="0.01"
            value={newBalance}
            onChange={(e) => setNewBalance(e.target.value)}
          />
          <Button
            isLoading={settingMain}
            onClick={() => switchBankId && setMain({ id: switchBankId, balance: parseFloat(newBalance) || 0 })}
          >
            Confirm switch
          </Button>
        </div>
      </Modal>

      {/* Edit payment method modal */}
      <Modal open={!!editMethod} onClose={() => setEditMethod(null)} title="Edit payment method">
        <div className="flex flex-col gap-3">
          <Input
            label="Name"
            type="text"
            value={editName}
            onChange={(e) => setEditName(e.target.value)}
          />
          {editMethod && LINKABLE_TYPES.includes(editMethod.type) && bankMethods.length > 0 && (
            <>
              <Select
                label="Linked bank"
                options={bankMethods.map((b) => ({ value: b.id, label: b.name }))}
                required
                value={editLinkedBankId}
                onChange={(e) => setEditLinkedBankId(e.target.value)}
              />
              {editLinkedBankId !== editMethod.linked_bank_id && (
                <Input
                  label="New link effective billing month"
                  type="date"
                  required
                  hint="The new bank applies from this first day of a billing month; earlier card activity stays with its historical bank."
                  value={editEffectiveBillingMonth}
                  onChange={(e) => setEditEffectiveBillingMonth(e.target.value)}
                />
              )}
            </>
          )}
          {editMethod?.type === 'credit_card' && (
            <label className="flex items-center gap-2 text-sm text-secondary cursor-pointer">
              <input
                type="checkbox"
                className="w-4 h-4"
                checked={editHasStampDuty}
                onChange={(e) => setEditHasStampDuty(e.target.checked)}
              />
              Stamp duty (imposta di bollo)
            </label>
          )}
          <Button
            isLoading={editing}
            disabled={!editName.trim() || (!!editMethod && LINKABLE_TYPES.includes(editMethod.type) && (!editLinkedBankId || (editLinkedBankId !== editMethod.linked_bank_id && !editEffectiveBillingMonth)))}
            onClick={() => {
              if (!editMethod) return;
              const linkChanged = LINKABLE_TYPES.includes(editMethod.type)
                && editLinkedBankId !== editMethod.linked_bank_id;
              editMutate({
                id: editMethod.id,
                name: editName,
                ...(linkChanged ? {
                  linked_bank_id: editLinkedBankId,
                  effective_billing_month: editEffectiveBillingMonth,
                } : {}),
                has_stamp_duty: editMethod.type === 'credit_card' ? editHasStampDuty : undefined,
              });
            }}
          >
            Save changes
          </Button>
        </div>
      </Modal>
    </div>
  );
}
