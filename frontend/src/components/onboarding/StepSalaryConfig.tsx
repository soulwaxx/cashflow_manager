import { useEffect, useMemo, useState } from 'react';
import { useForm } from 'react-hook-form';
import { useQuery } from '@tanstack/react-query';
import { useOnboarding, type SalaryPensionSetupDraft } from '../../contexts/OnboardingContext';
import { salaryApi } from '../../api/salary';
import { queryKeys } from '../../api/queryKeys';
import { Input } from '../ui/Input';
import { Button } from '../ui/Button';
import { fmt } from '../../utils/format';
import { percentToFraction, fractionToPercentText } from '../../utils/percent';

interface SetupFields {
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
}

const monthly = () => Array(12).fill(1) as number[];
const quarterly = () => [0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1];

export default function StepSalaryConfig() {
  const { updateData, setStep, data, salaryPensionDraft, setSalaryPensionDraft } = useOnboarding();
  const startMonth = data.tracking_start_date ?? '';
  const defaults: SetupFields = {
    salary_enabled: !!data.salary,
    pension_enabled: !!data.pension,
    ral: String(data.salary?.ral ?? ''),
    regional_tax_rate_pct: fractionToPercentText(data.salary?.regional_tax_rate ?? 0.0173),
    municipal_tax_rate_pct: fractionToPercentText(data.salary?.municipal_tax_rate ?? 0.001),
    meal_vouchers_annual: String(data.salary?.meal_vouchers_annual ?? 0),
    welfare_annual: String(data.salary?.welfare_annual ?? 0),
    salary_months: String(data.salary?.salary_months ?? 12) as '12' | '13' | '14',
    manual_net_override: data.salary?.manual_net_override == null ? '' : String(data.salary.manual_net_override),
    pension_name: data.pension?.name ?? '',
    pension_opening_balance: String(data.pension?.opening_balance ?? 0),
    pension_opening_balance_month: data.pension?.opening_balance_month ?? startMonth,
    employee_contrib_rate_pct: fractionToPercentText(data.pension?.employee_contrib_rate ?? 0),
    employee_contrib_annual_base: String(data.pension?.employee_contrib_annual_base ?? 0),
    employer_contrib_rate_pct: fractionToPercentText(data.pension?.employer_contrib_rate ?? 0),
    employer_contrib_annual_base: String(data.pension?.employer_contrib_annual_base ?? 0),
    tfr_contrib_annual: String(data.pension?.tfr_contrib_annual ?? 0),
    contribution_periods_by_month: data.pension?.contribution_periods_by_month ?? monthly(),
  };
  const formDefaults: SetupFields = salaryPensionDraft ? { ...defaults, ...salaryPensionDraft } : defaults;
  const [calendarPreset, setCalendarPreset] = useState<SalaryPensionSetupDraft['calendar_preset']>(() => salaryPensionDraft?.calendar_preset ?? (formDefaults.contribution_periods_by_month.every((weight) => weight === 1) ? 'monthly' : formDefaults.contribution_periods_by_month.join(',') === quarterly().join(',') ? 'quarterly' : 'custom'));
  const [validationError, setValidationError] = useState('');
  const { register, watch, handleSubmit, setValue } = useForm<SetupFields>({ defaultValues: formDefaults });
  const values = watch();
  useEffect(() => {
    const draft: SalaryPensionSetupDraft = { ...values, calendar_preset: calendarPreset };
    if (JSON.stringify(draft) !== JSON.stringify(salaryPensionDraft)) setSalaryPensionDraft(draft);
  }, [values, calendarPreset, salaryPensionDraft, setSalaryPensionDraft]);
  const regionalRate = percentToFraction(values.regional_tax_rate_pct);
  const municipalRate = percentToFraction(values.municipal_tax_rate_pct);
  const employeeRate = percentToFraction(values.employee_contrib_rate_pct);
  const employerRate = percentToFraction(values.employer_contrib_rate_pct);
  const percentRatesValid = regionalRate !== undefined && municipalRate !== undefined && (!values.pension_enabled || (employeeRate !== undefined && employerRate !== undefined));
  const salaryInput = useMemo(() => ({
    ral: Number(values.ral),
    regional_tax_rate: percentToFraction(values.regional_tax_rate_pct) ?? 0,
    municipal_tax_rate: percentToFraction(values.municipal_tax_rate_pct) ?? 0,
    meal_vouchers_annual: Number(values.meal_vouchers_annual || 0),
    welfare_annual: Number(values.welfare_annual || 0),
    salary_months: Number(values.salary_months) as 12 | 13 | 14,
  }), [values.ral, values.regional_tax_rate_pct, values.municipal_tax_rate_pct, values.meal_vouchers_annual, values.welfare_annual, values.salary_months, values.manual_net_override]);
  const pensionInput = useMemo(() => values.pension_enabled ? {
    employee_contrib_rate: percentToFraction(values.employee_contrib_rate_pct) ?? 0,
    employee_contrib_annual_base: Number(values.employee_contrib_annual_base || 0),
    employer_contrib_rate: percentToFraction(values.employer_contrib_rate_pct) ?? 0,
    employer_contrib_annual_base: Number(values.employer_contrib_annual_base || 0),
    tfr_contrib_annual: Number(values.tfr_contrib_annual || 0),
  } : null, [values.pension_enabled, values.employee_contrib_rate_pct, values.employee_contrib_annual_base, values.employer_contrib_rate_pct, values.employer_contrib_annual_base, values.tfr_contrib_annual]);
  const previewEligible = values.salary_enabled && Number(values.ral) > 0 && percentRatesValid && /^\d{4}-\d{2}-01$/.test(startMonth);
  const previewQuery = useQuery({
    queryKey: queryKeys.salary.calculate({ as_of: startMonth, salary: salaryInput, pension: pensionInput }),
    queryFn: () => salaryApi.calculate({ as_of: startMonth, salary: salaryInput, pension: pensionInput }),
    enabled: previewEligible,
    retry: false,
  });

  const onSubmit = (form: SetupFields) => {
    setValidationError('');
    const draft: SalaryPensionSetupDraft = { ...form, calendar_preset: calendarPreset };
    setSalaryPensionDraft(draft);
    const regional = percentToFraction(form.regional_tax_rate_pct);
    const municipal = percentToFraction(form.municipal_tax_rate_pct);
    const employee = percentToFraction(form.employee_contrib_rate_pct);
    const employer = percentToFraction(form.employer_contrib_rate_pct);
    const finiteNonnegative = (value: string) => value.trim() !== '' && Number.isFinite(Number(value)) && Number(value) >= 0;
    if (form.salary_enabled && (!finiteNonnegative(form.ral) || Number(form.ral) <= 0 || regional === undefined || municipal === undefined || !finiteNonnegative(form.meal_vouchers_annual) || !finiteNonnegative(form.welfare_annual) || (form.manual_net_override !== '' && !finiteNonnegative(form.manual_net_override)))) {
      setValidationError('Salary is enabled: enter a positive RAL, nonnegative amounts, and tax rates from 0–100% with at most two decimal places.');
      return;
    }
    const calendarValid = form.contribution_periods_by_month.length === 12 && form.contribution_periods_by_month.every((weight) => Number.isInteger(weight) && weight >= 0) && form.contribution_periods_by_month.some((weight) => weight > 0);
    if (form.pension_enabled && (!form.pension_name.trim() || !/^\d{4}-\d{2}-\d{2}$/.test(form.pension_opening_balance_month) || !finiteNonnegative(form.pension_opening_balance) || employee === undefined || employer === undefined || !finiteNonnegative(form.employee_contrib_annual_base) || !finiteNonnegative(form.employer_contrib_annual_base) || !finiteNonnegative(form.tfr_contrib_annual) || !calendarValid)) {
      setValidationError('Pension is enabled: enter a nonblank account name, opening month, nonnegative amounts, rates from 0–100% with at most two decimal places, and twelve nonnegative integer weights with a positive total.');
      return;
    }
    const salary = form.salary_enabled ? {
      ral: Number(form.ral), regional_tax_rate: regional!, municipal_tax_rate: municipal!,
      meal_vouchers_annual: Number(form.meal_vouchers_annual || 0), welfare_annual: Number(form.welfare_annual || 0),
      salary_months: Number(form.salary_months) as 12 | 13 | 14,
      manual_net_override: form.manual_net_override === '' ? null : Number(form.manual_net_override),
    } : undefined;
    const pension = form.pension_enabled ? {
      name: form.pension_name.trim(), opening_balance: Number(form.pension_opening_balance || 0),
      opening_balance_month: `${form.pension_opening_balance_month.slice(0, 7)}-01`,
      employee_contrib_rate: employee!, employee_contrib_annual_base: Number(form.employee_contrib_annual_base || 0),
      employer_contrib_rate: employer!, employer_contrib_annual_base: Number(form.employer_contrib_annual_base || 0),
      tfr_contrib_annual: Number(form.tfr_contrib_annual || 0), contribution_periods_by_month: form.contribution_periods_by_month,
    } : undefined;
    setValidationError('');
    updateData({ salary, pension });
    setStep(8);
  };

  const calendar = values.contribution_periods_by_month ?? monthly();
  return <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4">
    <h2 className="text-lg font-semibold">Optional salary and pension setup</h2>
    <p className="text-sm text-secondary">Both sections are optional and independent. Preview and save use tracking month {startMonth || '—'}.</p>
    <label className="flex items-center gap-2"><input type="checkbox" {...register('salary_enabled')} /> Configure salary</label>
    {values.salary_enabled && <section className="space-y-3 rounded border p-3"><h3 className="font-medium">Salary</h3>
      <Input label="RAL (€)" type="number" min="0.01" step="0.01" {...register('ral')} />
      <Input label="Regional tax rate (%)" type="number" min="0" max="100" step="any" {...register('regional_tax_rate_pct')} />
      <Input label="Municipal tax rate (%)" type="number" min="0" max="100" step="any" {...register('municipal_tax_rate_pct')} />
      <Input label="Meal vouchers annual (€)" type="number" min="0" step="0.01" {...register('meal_vouchers_annual')} />
      <Input label="Welfare annual (€)" type="number" min="0" step="0.01" {...register('welfare_annual')} />
      <label className="text-sm">Salary payments/year<select aria-label="Salary payments per year" {...register('salary_months')} className="block w-full border rounded p-2 bg-elevated"><option value="12">12</option><option value="13">13</option><option value="14">14</option></select></label>
      <Input label="Manual net override (€ per salary payment)" type="number" min="0" step="0.01" {...register('manual_net_override')} />
    </section>}
    <label className="flex items-center gap-2"><input type="checkbox" {...register('pension_enabled')} /> Configure pension</label>
    {values.pension_enabled && <section className="space-y-3 rounded border p-3"><h3 className="font-medium">Pension</h3>
      <Input label="Pension account name" type="text" {...register('pension_name')} />
      <Input label="Opening balance (€) at start of month" type="number" min="0" step="0.01" {...register('pension_opening_balance')} />
      <Input label="Opening balance month (saved as first of month)" type="date" {...register('pension_opening_balance_month')} />
      <p className="text-xs text-secondary">Opening amount is the start-of-month baseline; the setup tracking/effective month is {startMonth}.</p>
      <Input label="Employee contribution rate (%)" type="number" min="0" max="100" step="any" {...register('employee_contrib_rate_pct')} />
      <Input label="Employee annual base (€)" type="number" min="0" step="0.01" {...register('employee_contrib_annual_base')} />
      <Input label="Employer contribution rate (%)" type="number" min="0" max="100" step="any" {...register('employer_contrib_rate_pct')} />
      <Input label="Employer annual base (€)" type="number" min="0" step="0.01" {...register('employer_contrib_annual_base')} />
      <Input label="Annual TFR contribution (€)" type="number" min="0" step="0.01" {...register('tfr_contrib_annual')} />
      <label className="text-sm">Credit calendar preset<select aria-label="Setup credit calendar preset" value={calendarPreset} onChange={(e) => { setCalendarPreset(e.target.value as SalaryPensionSetupDraft['calendar_preset']); if (e.target.value === 'quarterly') setValue('contribution_periods_by_month', quarterly()); if (e.target.value === 'monthly') setValue('contribution_periods_by_month', monthly()); }} className="block w-full border rounded p-2 bg-elevated"><option value="monthly">Monthly</option><option value="quarterly">Quarterly (Mar/Jun/Sep/Dec)</option><option value="custom">Custom weights</option></select></label>
      <fieldset className="grid grid-cols-3 gap-2"><legend className="text-sm font-medium">January–December integer weights</legend>{calendar.map((weight, index) => <label key={index} className="text-xs">{new Date(2000,index,1).toLocaleString('en',{month:'short'})}<input aria-label={`${new Date(2000,index,1).toLocaleString('en',{month:'long'})} setup weight`} type="number" min="0" step="1" value={weight} onChange={(e) => { setCalendarPreset('custom'); setValue('contribution_periods_by_month', calendar.map((v,i) => i === index ? Number(e.target.value) : v)); }} className="block w-full border rounded p-2 bg-elevated" /></label>)}</fieldset>
      {calendar.some((weight) => !Number.isInteger(weight) || weight < 0) || calendar.every((weight) => weight === 0) ? <p role="alert" className="text-sm text-red-600">Enter twelve nonnegative integer weights with a positive total.</p> : null}
    </section>}
    {values.salary_enabled && !percentRatesValid && <p role="alert" className="text-sm text-red-600">Rates must be from 0–100% with at most two decimal places.</p>}
    {validationError && <p role="alert" className="text-sm text-red-600">{validationError}</p>}
    {previewEligible && previewQuery.isError && <p role="alert" className="text-sm text-red-600">Could not preview salary for {startMonth}; check the selected period and tax configuration.</p>}
    {previewEligible && previewQuery.data && <div role="status" className="rounded bg-blue-50 dark:bg-blue-900/20 p-3 text-sm"><strong>Backend estimate at {startMonth}: €{fmt(previewQuery.data.computed_net_monthly)} average net per salary payment ({previewQuery.data.salary_months}/year)</strong><p>Tax cap €{fmt(previewQuery.data.pension_deductibility_cap)} effective {previewQuery.data.tax_config_valid_from}; employee pension payroll deduction €{fmt(previewQuery.data.pension_payroll_deduction_annual)} annualized.</p></div>}
    <div className="flex flex-wrap gap-2"><Button variant="secondary" type="button" onClick={() => setStep(6)}>Back</Button><Button variant="ghost" type="button" onClick={() => { updateData({ salary: undefined, pension: undefined }); setSalaryPensionDraft(null); setStep(8); }}>Skip both</Button><Button type="submit">Next</Button></div>
  </form>;
}
