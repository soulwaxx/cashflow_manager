import { useForm } from 'react-hook-form';
import { useOnboarding } from '../../contexts/OnboardingContext';
import { Input } from '../ui/Input';
import { Button } from '../ui/Button';

interface Fields { name: string; opening_balance: string; }

export default function StepMainBank() {
  const { updateData, setStep, data } = useOnboarding();
  const { register, handleSubmit } = useForm<Fields>({
    defaultValues: {
      name: data.main_bank?.name ?? '',
      opening_balance:
        data.main_bank?.opening_balance != null ? String(data.main_bank.opening_balance) : '',
    },
  });

  const onSubmit = (d: Fields) => {
    updateData({ main_bank: { name: d.name, opening_balance: parseFloat(d.opening_balance) } });
    setStep(3);
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4">
      <h2 className="text-lg font-semibold">Main bank account</h2>
      <Input label="Account name" type="text" {...register('name', { required: true })} />
      <Input label="Current balance (€)" type="number" step="0.01" {...register('opening_balance', { required: true })} />
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" type="button" onClick={() => setStep(1)}>Back</Button>
        <Button type="submit">Next</Button>
      </div>
    </form>
  );
}
