import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useOnboarding } from '../../contexts/OnboardingContext';
import { onboardingApi } from '../../api/onboarding';
import { queryKeys } from '../../api/queryKeys';
import { Button } from '../ui/Button';
import type { OnboardingPayload } from '../../types/api';

export default function StepReview() {
  const { data, setStep } = useOnboarding();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const { mutate, isPending } = useMutation({
    mutationFn: () => onboardingApi.submit(data as OnboardingPayload),
    onSuccess: () => {
      qc.setQueryData(queryKeys.onboarding.status, { complete: true });
      navigate('/');
    },
    onError: () => setError('Submission failed. Please try again.'),
  });

  return (
    <div className="flex flex-col gap-4">
      <h2 className="text-lg font-semibold">Review & confirm</h2>
      <div className="text-sm text-secondary space-y-2 bg-subtle border border-line rounded-xl p-4 break-words">
        <div><strong>Start date:</strong> {data.tracking_start_date ?? '—'}</div>
        <div><strong>Main bank:</strong> {data.main_bank?.name ?? '—'} (€{data.main_bank?.opening_balance?.toFixed(2) ?? '0.00'})</div>
        <div><strong>Additional banks:</strong> {data.additional_banks?.length ?? 0}</div>
        <div><strong>Payment methods:</strong> {data.payment_methods?.length ?? 0}</div>
        <div><strong>Saving accounts:</strong> {data.saving_accounts?.length ?? 0}</div>
        <div><strong>Investment accounts:</strong> {data.investment_accounts?.length ?? 0}</div>
        {data.salary && <div><strong>RAL:</strong> €{data.salary.ral.toLocaleString()}</div>}
      </div>
      {error && <div role="alert" className="text-sm text-red-600">{error}</div>}
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" type="button" onClick={() => setStep(7)}>Back</Button>
        <Button onClick={() => mutate()} isLoading={isPending}>Confirm & start</Button>
      </div>
    </div>
  );
}
