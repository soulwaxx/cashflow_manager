import { useState } from 'react';
import { useOnboarding } from '../../contexts/OnboardingContext';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import type { PaymentMethod } from '../../types/api';

type PMType = PaymentMethod['type'];
const PM_TYPES: PMType[] = ['debit_card', 'credit_card', 'revolving', 'prepaid', 'cash'];

interface PM { name: string; type: PMType; linked_bank_name?: string; }

export default function StepPaymentMethods() {
  const { updateData, setStep, data } = useOnboarding();
  const [methods, setMethods] = useState<PM[]>(data.payment_methods ?? []);
  const [name, setName] = useState('');
  const [type, setType] = useState<PMType>('debit_card');
  const [linked, setLinked] = useState('');

  const add = () => {
    if (!name || (isBankFundedCard && !linked)) return;
    setMethods((prev) => [...prev, { name, type, linked_bank_name: linked || undefined }]);
    setName('');
    setLinked('');
  };

  const next = () => {
    updateData({ payment_methods: methods });
    setStep(5);
  };

  const mainBankName = data.main_bank?.name;
  const isBankFundedCard = type === 'debit_card' || type === 'credit_card' || type === 'revolving';

  return (
    <div className="flex flex-col gap-4">
      <h2 className="text-lg font-semibold">Payment methods (optional)</h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Input label="Name" type="text" value={name} onChange={(e) => setName(e.target.value)} />
        <div className="flex flex-col gap-1">
          <label htmlFor="setup-payment-type" className="text-sm font-medium text-secondary">Type</label>
          <select
            id="setup-payment-type"
            className="w-full min-h-11 border border-line-strong rounded-lg px-3 py-2 text-base sm:text-sm bg-elevated text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600"
            value={type}
            onChange={(e) => setType(e.target.value as PMType)}
          >
            {PM_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
        {isBankFundedCard && mainBankName && (
          <Input label="Linked bank" type="text" required value={linked} onChange={(e) => setLinked(e.target.value)} placeholder={mainBankName} />
        )}
        <Button variant="secondary" type="button" onClick={add} className="self-end sm:col-span-2 sm:justify-self-start">Add</Button>
      </div>
      {methods.length > 0 && (
        <ul className="text-sm space-y-1">
          {methods.map((m, i) => (
            <li key={i} className="flex flex-wrap justify-between gap-2 border border-line bg-subtle rounded-lg px-3 py-2 break-words">
              <span>{m.name}</span>
              <span className="text-muted">{m.type}</span>
            </li>
          ))}
        </ul>
      )}
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" type="button" onClick={() => setStep(3)}>Back</Button>
        <Button type="button" onClick={next}>Next</Button>
      </div>
    </div>
  );
}
