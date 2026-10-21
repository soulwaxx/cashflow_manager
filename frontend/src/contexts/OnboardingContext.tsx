import React, { createContext, useContext, useState } from 'react';
import type { OnboardingPayload } from '../types/api';

export interface SalaryPensionSetupDraft {
  salary_enabled: boolean;
  pension_enabled: boolean;
  ral: string;
  regional_tax_rate_pct: string;
  municipal_tax_rate_pct: string;
  meal_vouchers_annual: string;
  welfare_annual: string;
  salary_months: '12' | '13' | '14';
  manual_net_override: string;
  pension_name: string;
  pension_opening_balance: string;
  pension_opening_balance_month: string;
  employee_contrib_rate_pct: string;
  employee_contrib_annual_base: string;
  employer_contrib_rate_pct: string;
  employer_contrib_annual_base: string;
  tfr_contrib_annual: string;
  contribution_periods_by_month: number[];
  calendar_preset: 'monthly' | 'quarterly' | 'custom';
}

interface OnboardingState {
  step: number;
  data: Partial<OnboardingPayload>;
  salaryPensionDraft: SalaryPensionSetupDraft | null;
  setStep: (n: number) => void;
  updateData: (patch: Partial<OnboardingPayload>) => void;
  setSalaryPensionDraft: (draft: SalaryPensionSetupDraft | null) => void;
}

const OnboardingContext = createContext<OnboardingState | null>(null);

export function OnboardingProvider({ children }: { children: React.ReactNode }) {
  const [step, setStep] = useState(1);
  const [data, setData] = useState<Partial<OnboardingPayload>>({});
  const [salaryPensionDraft, setSalaryPensionDraft] = useState<SalaryPensionSetupDraft | null>(null);

  const updateData = (patch: Partial<OnboardingPayload>) =>
    setData((prev) => ({ ...prev, ...patch }));

  return (
    <OnboardingContext.Provider value={{ step, data, salaryPensionDraft, setStep, updateData, setSalaryPensionDraft }}>
      {children}
    </OnboardingContext.Provider>
  );
}

export function useOnboarding() {
  const ctx = useContext(OnboardingContext);
  if (!ctx) throw new Error('useOnboarding must be used inside OnboardingProvider');
  return ctx;
}
