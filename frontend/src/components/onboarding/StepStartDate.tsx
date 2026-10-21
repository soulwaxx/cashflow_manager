import { useForm } from 'react-hook-form';
import { useOnboarding } from '../../contexts/OnboardingContext';
import { Input } from '../ui/Input';
import { Button } from '../ui/Button';

export default function StepStartDate() {
  const { updateData, setStep, data } = useOnboarding();
  const { register, handleSubmit } = useForm<{ tracking_start_date: string }>({
    defaultValues: { tracking_start_date: data.tracking_start_date ?? '' },
  });

  const onSubmit = (d: { tracking_start_date: string }) => {
    const month = d.tracking_start_date.slice(0, 7);
    updateData({ tracking_start_date: `${month}-01` });
    setStep(2);
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4">
      <h2 className="text-lg font-semibold">When do you want to start tracking?</h2>
      <Input
        label="Tracking start month (saved as the first day of the month)"
        type="date"
        {...register('tracking_start_date', { required: true })}
      />
      <Button type="submit">Next</Button>
    </form>
  );
}
