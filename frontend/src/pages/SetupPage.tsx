import React from 'react';
import { OnboardingProvider, useOnboarding } from '../contexts/OnboardingContext';
import WizardProgress from '../components/onboarding/WizardProgress';
import StepStartDate from '../components/onboarding/StepStartDate';
import StepMainBank from '../components/onboarding/StepMainBank';
import StepAdditionalBanks from '../components/onboarding/StepAdditionalBanks';
import StepPaymentMethods from '../components/onboarding/StepPaymentMethods';
import StepSavingAccounts from '../components/onboarding/StepSavingAccounts';
import StepInvestmentAccounts from '../components/onboarding/StepInvestmentAccounts';
import StepSalaryConfig from '../components/onboarding/StepSalaryConfig';
import StepReview from '../components/onboarding/StepReview';

const STEPS: Record<number, React.ComponentType> = {
  1: StepStartDate,
  2: StepMainBank,
  3: StepAdditionalBanks,
  4: StepPaymentMethods,
  5: StepSavingAccounts,
  6: StepInvestmentAccounts,
  7: StepSalaryConfig,
  8: StepReview,
};

function WizardContent() {
  const { step } = useOnboarding();
  const Step = STEPS[step];
  return (
    <main className="min-h-dvh bg-canvas flex items-start justify-center px-4 py-6 sm:py-12">
      <div className="bg-surface rounded-2xl shadow-sm border border-line p-5 sm:p-8 w-full max-w-2xl min-w-0 text-primary">
        <p className="text-sm font-semibold tracking-wide text-blue-800 dark:text-blue-300 mb-2">CashFlow Manager</p>
        <h1 className="text-2xl font-bold mb-4 text-primary">Setup your account</h1>
        <WizardProgress current={step} total={8} />
        <Step />
      </div>
    </main>
  );
}

export default function SetupPage() {
  return (
    <OnboardingProvider>
      <WizardContent />
    </OnboardingProvider>
  );
}
