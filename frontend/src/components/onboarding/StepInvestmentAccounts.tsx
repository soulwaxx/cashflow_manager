import { useState } from 'react';
import { useOnboarding } from '../../contexts/OnboardingContext';
import { Input } from '../ui/Input';
import { Button } from '../ui/Button';

interface Account { name: string; opening_balance: number; }

export default function StepInvestmentAccounts() {
  const { updateData, setStep, data } = useOnboarding();
  const [accounts, setAccounts] = useState<Account[]>(data.investment_accounts ?? []);
  const [name, setName] = useState('');
  const [balance, setBalance] = useState('');

  const add = () => {
    if (!name) return;
    setAccounts((prev) => [...prev, { name, opening_balance: parseFloat(balance) || 0 }]);
    setName(''); setBalance('');
  };

  return (
    <div className="flex flex-col gap-4">
      <h2 className="text-lg font-semibold">Investment accounts (optional)</h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Input label="Account name" type="text" value={name} onChange={(e) => setName(e.target.value)} />
        <Input label="Balance (€)" type="number" step="0.01" value={balance} onChange={(e) => setBalance(e.target.value)} />
        <Button variant="secondary" type="button" onClick={add} className="self-end sm:col-span-2 sm:justify-self-start">Add</Button>
      </div>
      {accounts.length > 0 && (
        <ul className="text-sm space-y-1">
          {accounts.map((a, i) => <li key={i} className="border border-line bg-subtle rounded-lg px-3 py-2 flex flex-wrap justify-between gap-2 break-words"><span>{a.name}</span><span>€{a.opening_balance.toFixed(2)}</span></li>)}
        </ul>
      )}
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" type="button" onClick={() => setStep(5)}>Back</Button>
        <Button type="button" onClick={() => { updateData({ investment_accounts: accounts }); setStep(7); }}>Next</Button>
      </div>
    </div>
  );
}
