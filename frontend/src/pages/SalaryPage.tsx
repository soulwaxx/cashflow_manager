import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { accountsApi } from '../api/accounts';
import { pensionApi } from '../api/pension';
import type { PensionConfig, PensionConfigInput } from '../api/pension';
import { salaryApi } from '../api/salary';
import type { SalaryConfigCreate } from '../api/salary';
import type { SalaryConfig } from '../types/api';
import { queryKeys, invalidateFor } from '../api/queryKeys';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import Modal from '../components/ui/Modal';
import { fmt } from '../utils/format';
import { percentToFraction, fractionToPercentText } from '../utils/percent';

const monthNow = () => `${new Date().toISOString().slice(0, 7)}-01`;
const blankCalendar = () => Array(12).fill(1) as number[];
const quarterlyCalendar = () => [0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1];
export function errorMessage(error: unknown): string {
  const fallback = 'Unable to save. Please check the values and try again.';
  if (!error || typeof error !== 'object' || !('response' in error)) return fallback;
  const response = (error as { response?: unknown }).response;
  if (!response || typeof response !== 'object' || !('data' in response)) return fallback;
  const data = (response as { data?: unknown }).data;
  if (!data || typeof data !== 'object' || !('detail' in data)) return fallback;
  const detail = (data as { detail?: unknown }).detail;
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const messages = detail.map((entry: unknown) => {
      if (typeof entry === 'string') return entry;
      if (entry && typeof entry === 'object' && 'msg' in entry && typeof entry.msg === 'string') return entry.msg;
      return undefined;
    }).filter((message): message is string => Boolean(message?.trim()));
    if (messages.length) return messages.join('; ');
  }
  return fallback;
}

function SalaryForm({ initial, onSave, saving }: { initial?: SalaryConfig; onSave: (body: SalaryConfigCreate) => void; saving: boolean }) {
  const [error, setError] = useState('');
  const submit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const d = new FormData(event.currentTarget);
    const num = (key: string) => Number(d.get(key) || 0);
    const selectedDate = String(d.get('valid_from') || initial?.valid_from || '');
    const validFrom = /^\d{4}-\d{2}-\d{2}$/.test(selectedDate) ? `${selectedDate.slice(0, 7)}-01` : '';
    const regionalRate = percentToFraction(String(d.get('regional_tax_rate') ?? ''));
    const municipalRate = percentToFraction(String(d.get('municipal_tax_rate') ?? ''));
    if (!validFrom || num('ral') <= 0 || regionalRate === undefined || municipalRate === undefined) {
      setError('Enter a valid effective month and positive RAL; rates must be 0–100% with at most two decimal places.');
      return;
    }
    setError('');
    onSave({
      valid_from: validFrom,
      ral: num('ral'),
      regional_tax_rate: regionalRate,
      municipal_tax_rate: municipalRate,
      meal_vouchers_annual: num('meal_vouchers_annual'),
      welfare_annual: num('welfare_annual'),
      salary_months: num('salary_months') as 12 | 13 | 14,
      manual_net_override: d.get('manual_net_override') === '' ? null : num('manual_net_override'),
    });
  };
  return <form onSubmit={submit} className="flex flex-col gap-3">
    <Input label="Effective from (first day of month)" type="date" name="valid_from" defaultValue={initial?.valid_from ?? ''} required />
    <Input label="RAL (€)" type="number" name="ral" min="0.01" step="0.01" defaultValue={initial?.ral ?? ''} required />
    <Input label="Regional tax rate (%)" type="number" name="regional_tax_rate" min="0" max="100" step="any" defaultValue={fractionToPercentText(initial?.regional_tax_rate ?? 0.0173)} required />
    <Input label="Municipal tax rate (%)" type="number" name="municipal_tax_rate" min="0" max="100" step="any" defaultValue={fractionToPercentText(initial?.municipal_tax_rate ?? 0.001)} required />
    <Input label="Meal vouchers annual (€)" type="number" name="meal_vouchers_annual" min="0" step="0.01" defaultValue={initial?.meal_vouchers_annual ?? 0} />
    <Input label="Welfare annual (€)" type="number" name="welfare_annual" min="0" step="0.01" defaultValue={initial?.welfare_annual ?? 0} />
    <label className="text-sm font-medium">Salary payments per year<select name="salary_months" defaultValue={initial?.salary_months ?? 12} className="mt-1 block w-full border rounded p-2 bg-elevated"><option value="12">12</option><option value="13">13</option><option value="14">14</option></select></label>
    <Input label="Manual net override (€ per salary payment)" type="number" name="manual_net_override" min="0" step="0.01" defaultValue={initial?.manual_net_override ?? ''} hint="Leave blank to clear the override and use the computed estimate." />
    {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
    <Button type="submit" isLoading={saving}>Save salary period</Button>
  </form>;
}

function PensionForm({ initial, accounts, accountsLoading, accountsError, retryAccounts, onSave, saving }: { initial?: PensionConfig; accounts: Array<{id:string;name:string}>; accountsLoading: boolean; accountsError: boolean; retryAccounts: () => void; onSave: (body: PensionConfigInput) => void; saving: boolean }) {
  const [weights, setWeights] = useState(initial?.contribution_periods_by_month ?? blankCalendar());
  const [selectedAccountId, setSelectedAccountId] = useState(initial?.account_id ?? '');
  const canSaveDestination = !accountsLoading && !accountsError && accounts.some((account) => account.id === selectedAccountId);
  const [preset, setPreset] = useState(() => {
    const values = initial?.contribution_periods_by_month;
    if (values?.every((weight) => weight === 1)) return 'monthly';
    if (values?.join(',') === quarterlyCalendar().join(',')) return 'quarterly';
    return 'custom';
  });
  const [error, setError] = useState('');
  const submit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canSaveDestination) {
      setError('Select an active owned pension account from the available list after account lookup completes.');
      return;
    }
    const d = new FormData(event.currentTarget);
    const n = (key: string) => Number(d.get(key) || 0);
    const selectedDate = String(d.get('valid_from') || initial?.valid_from || '');
    const valid_from = /^\d{4}-\d{2}-\d{2}$/.test(selectedDate) ? `${selectedDate.slice(0, 7)}-01` : '';
    const employeeRate = percentToFraction(String(d.get('employee_rate') ?? ''));
    const employerRate = percentToFraction(String(d.get('employer_rate') ?? ''));
    if (!valid_from || employeeRate === undefined || employerRate === undefined || weights.some((w) => !Number.isInteger(w) || w < 0) || weights.every((w) => w === 0)) {
      setError('Use a first-of-month date, rates with at most two decimal places, and twelve nonnegative integer weights with a positive total.');
      return;
    }
    setError('');
    onSave({
      valid_from,
      account_id: selectedAccountId,
      employee_contrib_rate: employeeRate,
      employee_contrib_annual_base: n('employee_base'),
      employer_contrib_rate: employerRate,
      employer_contrib_annual_base: n('employer_base'),
      tfr_contrib_annual: n('tfr'),
      contribution_periods_by_month: weights,
    });
  };
  return <form onSubmit={submit} className="flex flex-col gap-3">
    <Input label="Effective from (first day of month)" name="valid_from" type="date" defaultValue={initial?.valid_from ?? ''} required />
    {accountsError && <div role="alert" className="text-sm text-red-600">Could not load active pension accounts. Retry the account lookup before selecting a destination.<Button type="button" variant="ghost" onClick={retryAccounts}>Retry accounts</Button></div>}
    {!accountsError && !accountsLoading && accounts.length === 0 && <p role="status" className="text-sm text-secondary">No active owned pension accounts are available. Create one in account setup before saving a pension period.</p>}
    <label className="text-sm font-medium">Active owned pension account<select name="account_id" value={selectedAccountId} onChange={(event) => { setSelectedAccountId(event.target.value); setError(''); }} required disabled={accountsError || accountsLoading || accounts.length === 0} className="mt-1 block w-full border rounded p-2 bg-elevated"><option value="">Choose an account</option>{accounts.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}</select></label>
    <p className="text-xs text-secondary">Annual bases are independent of RAL. New contribution values default to zero.</p>
    <Input label="Employee contribution rate (%)" name="employee_rate" type="number" min="0" max="100" step="any" defaultValue={fractionToPercentText(initial?.employee_contrib_rate ?? 0)} />
    <Input label="Employee annual base (€)" name="employee_base" type="number" min="0" step="0.01" defaultValue={initial?.employee_contrib_annual_base ?? 0} />
    <Input label="Employer contribution rate (%)" name="employer_rate" type="number" min="0" max="100" step="any" defaultValue={fractionToPercentText(initial?.employer_contrib_rate ?? 0)} />
    <Input label="Employer annual base (€)" name="employer_base" type="number" min="0" step="0.01" defaultValue={initial?.employer_contrib_annual_base ?? 0} />
    <Input label="Annual TFR contribution (€)" name="tfr" type="number" min="0" step="0.01" defaultValue={initial?.tfr_contrib_annual ?? 0} />
    <label className="text-sm font-medium">Credit calendar preset<select aria-label="Credit calendar preset" value={preset} onChange={(e) => { setPreset(e.target.value); if (e.target.value === 'monthly') setWeights(blankCalendar()); if (e.target.value === 'quarterly') setWeights(quarterlyCalendar()); }} className="mt-1 block w-full border rounded p-2 bg-elevated"><option value="custom">Custom monthly weights</option><option value="monthly">Monthly</option><option value="quarterly">Quarterly (Mar/Jun/Sep/Dec)</option></select></label>
    <fieldset className="grid grid-cols-3 gap-2"><legend className="text-sm font-medium mb-2">January–December credit weights (12 integers)</legend>{weights.map((weight, i) => <label key={i} className="text-xs text-secondary">{new Date(2000, i, 1).toLocaleString('en', { month: 'short' })}<input aria-label={`${new Date(2000, i, 1).toLocaleString('en', { month: 'long' })} credit weight`} type="number" min="0" step="1" value={weight} onChange={(e) => { setPreset('custom'); setWeights((old) => old.map((v, n) => n === i ? Number(e.target.value) : v)); }} className="block w-full border rounded p-2 bg-elevated" /></label>)}</fieldset>
    {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
    <Button type="submit" isLoading={saving} disabled={!canSaveDestination}>Save pension period</Button>
  </form>;
}

export default function SalaryPage() {
  const qc = useQueryClient();
  const [addSalary, setAddSalary] = useState(false);
  const [editSalary, setEditSalary] = useState<SalaryConfig | null>(null);
  const [addPension, setAddPension] = useState(false);
  const [editPension, setEditPension] = useState<PensionConfig | null>(null);
  const [asOf, setAsOf] = useState(monthNow());
  const [mutationError, setMutationError] = useState('');
  const salaries = useQuery({ queryKey: queryKeys.salary.list, queryFn: salaryApi.list });
  const pensions = useQuery({ queryKey: queryKeys.pension.configs, queryFn: pensionApi.listConfigs });
  const accounts = useQuery({ queryKey: queryKeys.accounts.all, queryFn: () => accountsApi.list() });
  const salaryConfigs = salaries.data ?? [];
  const pensionConfigs = pensions.data ?? [];
  const pensionAccounts = (accounts.data ?? []).filter((account) => account.type === 'pension' && account.is_active).map(({ id, name }) => ({ id, name }));
  const selectedSalary = useMemo(() => [...salaryConfigs].reverse().find((c) => c.valid_from <= asOf), [salaryConfigs, asOf]);
  const selectedPension = useMemo(() => [...pensionConfigs].reverse().find((c) => c.valid_from <= asOf), [pensionConfigs, asOf]);
  const pensionSummary = useQuery({ queryKey: queryKeys.pension.summaryFor(Number(asOf.slice(0, 4)), asOf), queryFn: () => pensionApi.summary(Number(asOf.slice(0, 4)), asOf), retry: false });
  const breakdown = useQuery({ queryKey: queryKeys.salary.breakdown(asOf), queryFn: () => salaryApi.breakdown(asOf), enabled: !!selectedSalary, retry: false });

  const refresh = () => { invalidateFor(qc, 'salary'); invalidateFor(qc, 'pension'); };
  const createSalary = useMutation({ mutationFn: salaryApi.create, onSuccess: () => { refresh(); setAddSalary(false); setMutationError(''); }, onError: (e) => setMutationError(errorMessage(e)) });
  const updateSalary = useMutation({ mutationFn: (body: SalaryConfigCreate) => salaryApi.update(editSalary!.id, body), onSuccess: () => { refresh(); setEditSalary(null); setMutationError(''); }, onError: (e) => setMutationError(errorMessage(e)) });
  const removeSalary = useMutation({ mutationFn: salaryApi.delete, onSuccess: refresh, onError: (e) => setMutationError(errorMessage(e)) });
  const createPension = useMutation({ mutationFn: pensionApi.createConfig, onSuccess: () => { refresh(); setAddPension(false); setMutationError(''); }, onError: (e) => setMutationError(errorMessage(e)) });
  const updatePension = useMutation({ mutationFn: (body: PensionConfigInput) => pensionApi.updateConfig(editPension!.id, body), onSuccess: () => { refresh(); setEditPension(null); setMutationError(''); }, onError: (e) => setMutationError(errorMessage(e)) });
  const removePension = useMutation({ mutationFn: pensionApi.deleteConfig, onSuccess: refresh, onError: (e) => setMutationError(errorMessage(e)) });

  return <main className="max-w-4xl space-y-6">
    <h1 className="text-xl font-bold text-primary">Salary and pension</h1>
    <label className="block max-w-xs text-sm font-medium">Selected effective/reporting month<Input label="Selected effective/reporting month" aria-label="Selected effective/reporting month" type="date" value={asOf} onChange={(e) => { const m = e.target.value.slice(0, 7); if (m) setAsOf(`${m}-01`); }} /></label>
    {mutationError && <p role="alert" className="text-sm text-red-600">{mutationError}</p>}
    <section aria-labelledby="salary-heading" className="space-y-3"><div className="flex justify-between items-center"><h2 id="salary-heading" className="text-lg font-semibold">Salary effective periods</h2><Button onClick={() => setAddSalary(true)}>Add salary period</Button></div>
      {salaries.isLoading ? <p>Loading salary periods…</p> : salaries.isError ? <p role="alert">Could not load salary periods. <Button variant="ghost" onClick={() => void salaries.refetch()}>Retry salary lookup</Button></p> : salaryConfigs.length === 0 ? <p>No salary period is required to configure pension.</p> : salaryConfigs.map((c) => <article key={c.id} className="rounded-xl border border-line bg-surface p-4"><div className="flex flex-wrap justify-between gap-2"><div><strong>From {c.valid_from}</strong><p>RAL €{fmt(c.ral)} · {c.salary_months} salary payments/year</p></div><div className="text-right"><strong>€{fmt(c.effective_net_monthly)}/payment</strong><p className="text-xs">Average net per salary payment ({c.salary_months}/year)</p>{c.manual_net_override != null && <p className="text-xs text-yellow-600">Manual override €{fmt(c.manual_net_override)}; computed €{fmt(c.computed_net_monthly)}</p>}</div></div><div className="mt-2 flex gap-2"><Button variant="ghost" onClick={() => setEditSalary(c)}>Edit</Button><Button variant="ghost" onClick={() => removeSalary.mutate(c.id)}>Delete</Button></div></article>)}</section>
    <section aria-labelledby="pension-heading" className="space-y-3"><div className="flex justify-between items-center"><h2 id="pension-heading" className="text-lg font-semibold">Pension effective periods</h2><Button onClick={() => setAddPension(true)}>Add pension period</Button></div>
      <p className="text-sm text-secondary">Scheduled contribution credits are estimates, not proof of fund receipts. Salary payment count and pension credit calendar are independent.</p>
      {accounts.isError && <p role="alert">Could not load account destinations. Pension periods remain viewable; retry accounts before adding or editing a destination. <Button variant="ghost" onClick={() => void accounts.refetch()}>Retry accounts</Button></p>}
      {pensions.isLoading ? <p>Loading pension periods…</p> : pensions.isError ? <p role="alert">Could not load pension periods. <Button variant="ghost" onClick={() => void pensions.refetch()}>Retry pension lookup</Button></p> : pensionConfigs.length === 0 ? <p>No pension period configured.</p> : pensionConfigs.map((c) => <article key={c.id} className="rounded-xl border border-line bg-surface p-4"><strong>From {c.valid_from}</strong><p>Account: {accounts.isError ? 'Account name lookup failed' : accounts.data?.find((a) => a.type === 'pension' && a.id === c.account_id)?.name ?? 'Account not in the active account list'} · employee base €{fmt(c.employee_contrib_annual_base)} · employer base €{fmt(c.employer_contrib_annual_base)} · TFR €{fmt(c.tfr_contrib_annual)}/year</p><div className="mt-2 flex gap-2"><Button variant="ghost" onClick={() => setEditPension(c)}>Edit</Button><Button variant="ghost" onClick={() => removePension.mutate(c.id)}>Delete</Button></div></article>)}</section>
    <section aria-labelledby="pension-summary-heading" className="rounded-xl border border-line bg-surface p-4 space-y-2"><h2 id="pension-summary-heading" className="text-lg font-semibold">Selected month pension summary · {asOf}</h2>{pensionSummary.isLoading ? <p>Loading pension summary…</p> : pensionSummary.isError ? <p role="alert">Could not load pension summary: {errorMessage(pensionSummary.error)} <Button variant="ghost" onClick={() => void pensionSummary.refetch()}>Retry pension summary</Button></p> : pensionSummary.data && <><p>Annualized employee €{fmt(pensionSummary.data.annualized.employee)} · employer €{fmt(pensionSummary.data.annualized.employer)} · TFR €{fmt(pensionSummary.data.annualized.tfr)}{pensionSummary.data.config ? ` · config effective ${pensionSummary.data.config.valid_from}` : ' · no pension configuration applies'}</p><p>Cap-eligible configured contributions €{fmt(pensionSummary.data.annualized.eligible_contributions)} · cap used €{fmt(pensionSummary.data.annualized.cap_used)} · cap excess €{fmt(pensionSummary.data.annualized.cap_excess)} · cap €{fmt(pensionSummary.data.annualized.cap)}</p><p className="text-xs text-secondary">{pensionSummary.data.annualized.cap_scope} · tax cap effective {pensionSummary.data.annualized.tax_config_valid_from}</p></>}</section>
    <section aria-labelledby="breakdown-heading" className="rounded-xl border border-line bg-surface p-4 space-y-2"><h2 id="breakdown-heading" className="text-lg font-semibold">Selected month breakdown · {asOf}</h2>{breakdown.isLoading ? <p>Loading selected-month breakdown…</p> : breakdown.data ? <><p>Salary period: {breakdown.data.salary_config_valid_from ?? 'Preview'} · pension period: {breakdown.data.pension_config_valid_from ?? 'None'} · tax effective: {breakdown.data.tax_config_valid_from}</p><p>Annual contribution flows — employee €{fmt(breakdown.data.employee_pension_contribution_annual)} · employer €{fmt(breakdown.data.employer_pension_contribution_annual)} · TFR €{fmt(breakdown.data.tfr_contribution_annual)}</p><p>Employee contribution withheld from cash net €{fmt(breakdown.data.employee_pension_contribution_annual)} · payroll taxable-base deduction €{fmt(breakdown.data.pension_payroll_deduction_annual)} · employer taxable excess €{fmt(breakdown.data.pension_employer_taxable_excess_annual)}. Employer and TFR flows are not direct cash deductions.</p><p>Configured eligible contributions €{fmt(breakdown.data.pension_cap_eligible_contributions_annual)} · cap used €{fmt(breakdown.data.pension_cap_used_annual)} / €{fmt(breakdown.data.pension_deductibility_cap)} · excess €{fmt(breakdown.data.pension_cap_excess_annual)}</p><p className="text-xs text-secondary">{breakdown.data.pension_cap_scope} · cap effective {breakdown.data.tax_config_valid_from}</p><p>Gross annual €{fmt(breakdown.data.gross_annual)} · social security €{fmt(breakdown.data.social_security)} · taxable base €{fmt(breakdown.data.taxable_base)}</p><p>Income tax gross €{fmt(breakdown.data.income_tax_gross)} · employment deduction €{fmt(breakdown.data.employment_deduction)} · income tax net €{fmt(breakdown.data.income_tax_net)} · regional surtax €{fmt(breakdown.data.regional_surtax)} · municipal surtax €{fmt(breakdown.data.municipal_surtax)}</p><p>Computed net annual €{fmt(breakdown.data.net_annual)} · computed net/payment €{fmt(breakdown.data.computed_net_monthly)} ({breakdown.data.salary_months} payments/year) · vouchers/month €{fmt(breakdown.data.meal_vouchers_monthly)} · welfare/month €{fmt(breakdown.data.welfare_monthly)}</p>{breakdown.data.manual_net_override != null && <p>Effective net/payment €{fmt(breakdown.data.effective_net_monthly ?? breakdown.data.manual_net_override)} · manual override €{fmt(breakdown.data.manual_net_override)} retained for comparison.</p>}</> : <p role="status">{breakdown.error ? errorMessage(breakdown.error) : selectedSalary ? 'Breakdown unavailable.' : selectedPension ? 'Pension period applies without a salary period.' : 'No salary period applies to this month.'}</p>}</section>
    <Modal open={addSalary} onClose={() => setAddSalary(false)} title="Add salary period"><SalaryForm onSave={(body) => createSalary.mutate(body)} saving={createSalary.isPending} /></Modal>
    <Modal open={!!editSalary} onClose={() => setEditSalary(null)} title="Edit salary period">{editSalary && <SalaryForm initial={editSalary} onSave={(body) => updateSalary.mutate(body)} saving={updateSalary.isPending} />}</Modal>
    <Modal open={addPension} onClose={() => setAddPension(false)} title="Add pension period"><PensionForm accounts={pensionAccounts} accountsLoading={accounts.isFetching} accountsError={accounts.isError} retryAccounts={() => void accounts.refetch()} onSave={(body) => createPension.mutate(body)} saving={createPension.isPending} /></Modal>
    <Modal open={!!editPension} onClose={() => setEditPension(null)} title="Edit pension period">{editPension && <PensionForm initial={editPension} accounts={pensionAccounts} accountsLoading={accounts.isFetching} accountsError={accounts.isError} retryAccounts={() => void accounts.refetch()} onSave={(body) => updatePension.mutate(body)} saving={updatePension.isPending} />}</Modal>
  </main>;
}
