import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes, Outlet } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';
import SetupPage from '../../src/pages/SetupPage';
import { salaryApi } from '../../src/api/salary';
import { queryKeys } from '../../src/api/queryKeys';
import { vi } from 'vitest';

// SetupPage now relies on the surrounding QueryClientProvider so it shares the
// same cache as the rest of the app.
function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

async function advanceToSalarySetup(user: ReturnType<typeof userEvent.setup>, month = '2026-07-01') {
  fireEvent.change(screen.getByLabelText(/tracking start month/i), { target: { value: month } });
  await user.click(screen.getByRole('button', { name: /next/i }));
  await user.type(await screen.findByLabelText(/account name/i), 'Main Bank');
  await user.type(screen.getByLabelText(/current balance/i), '100');
  await user.click(screen.getByRole('button', { name: /next/i }));
  for (let step = 0; step < 4; step += 1) await user.click(await screen.findByRole('button', { name: /next/i }));
  await screen.findByText('Optional salary and pension setup');
}

// ---------------------------------------------------------------------------
// Tests: SetupPage wizard content
// ---------------------------------------------------------------------------

test('SetupPage renders without crashing and shows wizard heading', async () => {
  render(<SetupPage />, { wrapper });
  expect(screen.getByText('Setup your account')).toBeInTheDocument();
});

test('SetupPage step 1 shows start-date heading', async () => {
  render(<SetupPage />, { wrapper });
  expect(screen.getByText('When do you want to start tracking?')).toBeInTheDocument();
});

test('SetupPage step 1 shows step indicator "Step 1 of 8"', async () => {
  render(<SetupPage />, { wrapper });
  expect(screen.getByText('Step 1 of 8')).toBeInTheDocument();
});

test('SetupPage step 1 has a Next button', async () => {
  render(<SetupPage />, { wrapper });
  expect(screen.getByRole('button', { name: /next/i })).toBeInTheDocument();
});

test('SetupPage normalizes tracking date to the first day of the selected month', async () => {
  const user = userEvent.setup();
  render(<SetupPage />, { wrapper });
  fireEvent.change(screen.getByLabelText(/tracking start month/i), { target: { value: '2026-04-17' } });
  await user.click(screen.getByRole('button', { name: /next/i }));
  await waitFor(() => expect(screen.getByText('Main bank account')).toBeInTheDocument());
  // Continue through required main bank and optional setup steps.
  await user.type(screen.getByLabelText(/account name/i), 'Main Bank');
  await user.type(screen.getByLabelText(/current balance/i), '100');
  await user.click(screen.getByRole('button', { name: /next/i }));
  await user.click(await screen.findByRole('button', { name: /next/i }));
  await user.click(await screen.findByRole('button', { name: /next/i }));
  await user.click(await screen.findByRole('button', { name: /next/i }));
  await user.click(await screen.findByRole('button', { name: /next/i }));
  await waitFor(() => expect(screen.getByText('Optional salary and pension setup')).toBeInTheDocument());
  expect(screen.getByText(/Preview and save use tracking month 2026-04-01/)).toBeInTheDocument();
});

test('SetupPage advances to step 2 after filling start date and clicking Next', async () => {
  const user = userEvent.setup();
  render(<SetupPage />, { wrapper });

  // Fill the required date field on step 1
  const dateInput = screen.getByLabelText(/tracking start month/i);
  fireEvent.change(dateInput, { target: { value: '2026-01-01' } });

  await user.click(screen.getByRole('button', { name: /next/i }));

  // Step 2 heading
  await waitFor(() =>
    expect(screen.getByText('Main bank account')).toBeInTheDocument()
  );
  expect(screen.getByText('Step 2 of 8')).toBeInTheDocument();
});

test('pension-only onboarding keeps salary absent and submits an explicit opening month', async () => {
  const user = userEvent.setup();
  let submitted: any;
  server.use(http.post('/api/v1/onboarding', async ({ request }) => { submitted = await request.json(); return HttpResponse.json({ ok: true }); }));
  render(<SetupPage />, { wrapper });
  fireEvent.change(screen.getByLabelText(/tracking start month/i), { target: { value: '2026-03-01' } });
  await user.click(screen.getByRole('button', { name: /next/i }));
  await user.type(await screen.findByLabelText(/account name/i), 'Main Bank');
  await user.type(screen.getByLabelText(/current balance/i), '100');
  await user.click(screen.getByRole('button', { name: /next/i }));
  await user.click(await screen.findByRole('button', { name: /next/i }));
  await user.click(await screen.findByRole('button', { name: /next/i }));
  await user.click(await screen.findByRole('button', { name: /next/i }));
  await user.click(await screen.findByRole('button', { name: /next/i }));
  await waitFor(() => expect(screen.getByText('Optional salary and pension setup')).toBeInTheDocument());
  await user.click(screen.getByLabelText(/configure pension/i));
  await user.type(screen.getByLabelText(/pension account name/i), 'Fund');
  fireEvent.change(screen.getByLabelText(/opening balance month \(saved as first of month\)/i), { target: { value: '2026-03-17' } });
  await user.click(screen.getByRole('button', { name: /^next$/i }));
  await waitFor(() => expect(screen.getByText(/^Pension:$/).parentElement).toHaveTextContent('Fund'));
  expect(screen.getByText(/^Salary:$/).parentElement).toHaveTextContent('not configured');
  await user.click(screen.getByRole('button', { name: /confirm & start/i }));
  await waitFor(() => expect(submitted).toBeTruthy());
  expect(submitted.tracking_start_date).toBe('2026-03-01');
  expect(submitted.salary).toBeUndefined();
  expect(submitted.pension).toMatchObject({ name: 'Fund', opening_balance_month: '2026-03-01', employee_contrib_rate: 0, employer_contrib_rate: 0, tfr_contrib_annual: 0, contribution_periods_by_month: Array(12).fill(1) });
});

test('salary-only onboarding previews and saves at tracking month without pension fields', async () => {
  const user = userEvent.setup();
  let previewRequest: any;
  let submitted: any;
  server.use(
    http.post('/api/v1/salary/calculate', async ({ request }) => { previewRequest = await request.json(); return HttpResponse.json({ gross_annual: 30000, social_security: 0, employee_pension_contribution_annual: 0, employer_pension_contribution_annual: 0, tfr_contribution_annual: 0, pension_payroll_deduction_annual: 0, pension_employer_taxable_excess_annual: 0, pension_cap_eligible_contributions_annual: 0, pension_cap_used_annual: 0, pension_cap_excess_annual: 0, pension_deductibility_cap: 5300, pension_cap_scope: 'configured payroll', tax_config_id: 'tax', tax_config_valid_from: '2026-01-01', taxable_base: 30000, income_tax_gross: 0, employment_deduction: 0, income_tax_net: 0, regional_surtax: 0, municipal_surtax: 0, net_annual: 30000, computed_net_monthly: 2500, meal_vouchers_monthly: 0, welfare_monthly: 0, salary_months: 12 }); }),
    http.post('/api/v1/onboarding', async ({ request }) => { submitted = await request.json(); return HttpResponse.json({ ok: true }); }),
  );
  render(<SetupPage />, { wrapper });
  fireEvent.change(screen.getByLabelText(/tracking start month/i), { target: { value: '2026-05-01' } });
  await user.click(screen.getByRole('button', { name: /next/i }));
  await user.type(await screen.findByLabelText(/account name/i), 'Main Bank');
  await user.type(screen.getByLabelText(/current balance/i), '100');
  await user.click(screen.getByRole('button', { name: /next/i }));
  await user.click(await screen.findByRole('button', { name: /next/i }));
  await user.click(await screen.findByRole('button', { name: /next/i }));
  await user.click(await screen.findByRole('button', { name: /next/i }));
  await user.click(await screen.findByRole('button', { name: /next/i }));
  await user.click(await screen.findByLabelText(/configure salary/i));
  await user.type(screen.getByLabelText(/ral/i), '30000');
  await waitFor(() => expect(previewRequest).toBeTruthy());
  await user.click(screen.getByRole('button', { name: /^next$/i }));
  await user.click(await screen.findByRole('button', { name: /confirm & start/i }));
  await waitFor(() => expect(submitted).toBeTruthy());
  expect(previewRequest.as_of).toBe('2026-05-01');
  expect(previewRequest.pension).toBeNull();
  expect(submitted.tracking_start_date).toBe(previewRequest.as_of);
  expect(submitted.salary.ral).toBe(30000);
  expect(submitted.pension).toBeUndefined();
});

test('salary and unsaved pension preview use independent bases and the exact saved month', async () => {
  const user = userEvent.setup();
  const previews: any[] = [];
  let submitted: any;
  server.use(
    http.post('/api/v1/salary/calculate', async ({ request }) => { previews.push(await request.json()); return HttpResponse.json({ gross_annual: 50000, social_security: 0, employee_pension_contribution_annual: 300, employer_pension_contribution_annual: 400, tfr_contribution_annual: 1200, pension_payroll_deduction_annual: 300, pension_employer_taxable_excess_annual: 0, pension_cap_eligible_contributions_annual: 700, pension_cap_used_annual: 700, pension_cap_excess_annual: 0, pension_deductibility_cap: 5300, pension_cap_scope: 'configured payroll', tax_config_id: 'tax', tax_config_valid_from: '2026-01-01', taxable_base: 50000, income_tax_gross: 0, employment_deduction: 0, income_tax_net: 0, regional_surtax: 0, municipal_surtax: 0, net_annual: 40000, computed_net_monthly: 3333.33, meal_vouchers_monthly: 0, welfare_monthly: 0, salary_months: 12 }); }),
    http.post('/api/v1/onboarding', async ({ request }) => { submitted = await request.json(); return HttpResponse.json({ ok: true }); }),
  );
  render(<SetupPage />, { wrapper });
  fireEvent.change(screen.getByLabelText(/tracking start month/i), { target: { value: '2026-06-01' } });
  await user.click(screen.getByRole('button', { name: /next/i }));
  await user.type(await screen.findByLabelText(/account name/i), 'Main Bank');
  await user.type(screen.getByLabelText(/current balance/i), '100');
  await user.click(screen.getByRole('button', { name: /next/i }));
  await user.click(await screen.findByRole('button', { name: /next/i }));
  await user.click(await screen.findByRole('button', { name: /next/i }));
  await user.click(await screen.findByRole('button', { name: /next/i }));
  await user.click(await screen.findByRole('button', { name: /next/i }));
  await user.click(await screen.findByLabelText(/configure salary/i));
  await user.type(screen.getByLabelText(/ral/i), '50000');
  await user.click(screen.getByLabelText(/configure pension/i));
  await user.type(screen.getByLabelText(/pension account name/i), 'New fund');
  fireEvent.change(screen.getByLabelText(/opening balance month/i), { target: { value: '2026-06-01' } });
  await user.clear(screen.getByLabelText(/employee contribution rate/i));
  await user.type(screen.getByLabelText(/employee contribution rate/i), '0.07');
  await user.clear(screen.getByLabelText(/employee annual base/i));
  await user.type(screen.getByLabelText(/employee annual base/i), '30000');
  await user.clear(screen.getByLabelText(/employer contribution rate/i));
  await user.type(screen.getByLabelText(/employer contribution rate/i), '2.01');
  await user.clear(screen.getByLabelText(/employer annual base/i));
  await user.type(screen.getByLabelText(/employer annual base/i), '20000');
  await waitFor(() => expect(previews[previews.length - 1]?.pension?.employee_contrib_annual_base).toBe(30000));
  await user.click(screen.getByRole('button', { name: /^next$/i }));
  await user.click(await screen.findByRole('button', { name: /confirm & start/i }));
  await waitFor(() => expect(submitted).toBeTruthy());
  const lastPreview = previews[previews.length - 1];
  expect(lastPreview).toMatchObject({ as_of: '2026-06-01', salary: { ral: 50000 }, pension: { employee_contrib_rate: 0.0007, employee_contrib_annual_base: 30000, employer_contrib_rate: 0.0201, employer_contrib_annual_base: 20000 } });
  expect(lastPreview.pension).not.toHaveProperty('account_id');
  expect(submitted.tracking_start_date).toBe(lastPreview.as_of);
  expect(submitted.salary.ral).toBe(50000);
  expect(submitted.pension).toMatchObject({ opening_balance_month: '2026-06-01', employee_contrib_rate: 0.0007, employee_contrib_annual_base: 30000, employer_contrib_rate: 0.0201, employer_contrib_annual_base: 20000 });
  expect(submitted.pension).not.toHaveProperty('account_id');
});

test('onboarding percentage preview sends an exact four-decimal fraction', async () => {
  const user = userEvent.setup();
  let preview: any;
  server.use(http.post('/api/v1/salary/calculate', async ({ request }) => {
    preview = await request.json();
    return HttpResponse.json({ gross_annual: 30000, social_security: 0, employee_pension_contribution_annual: 0, employer_pension_contribution_annual: 0, tfr_contribution_annual: 0, pension_payroll_deduction_annual: 0, pension_employer_taxable_excess_annual: 0, pension_cap_eligible_contributions_annual: 0, pension_cap_used_annual: 0, pension_cap_excess_annual: 0, pension_deductibility_cap: 5300, pension_cap_scope: 'Configured payroll', tax_config_id: 'tax', tax_config_valid_from: '2026-01-01', taxable_base: 30000, income_tax_gross: 0, employment_deduction: 0, income_tax_net: 0, regional_surtax: 0, municipal_surtax: 0, net_annual: 30000, computed_net_monthly: 2500, meal_vouchers_monthly: 0, welfare_monthly: 0, salary_months: 12 });
  }));
  render(<SetupPage />, { wrapper });
  await advanceToSalarySetup(user);
  await user.click(screen.getByLabelText(/configure salary/i));
  await user.type(screen.getByLabelText(/ral/i), '30000');
  await user.clear(screen.getByLabelText(/regional tax rate/i));
  await user.type(screen.getByLabelText(/regional tax rate/i), '0.07');
  await waitFor(() => expect(preview?.salary.regional_tax_rate).toBe(0.0007));
});

test('onboarding rejects blank pension names and zero-only contribution calendars', async () => {
  const user = userEvent.setup();
  render(<SetupPage />, { wrapper });
  await advanceToSalarySetup(user);
  await user.click(screen.getByLabelText(/configure pension/i));
  fireEvent.change(screen.getByLabelText(/pension account name/i), { target: { value: '   ' } });
  fireEvent.change(screen.getByLabelText(/opening balance month/i), { target: { value: '2026-07-01' } });
  await user.click(screen.getByRole('button', { name: /^next$/i }));
  expect(await screen.findByRole('alert')).toHaveTextContent(/nonblank account name/i);
  expect(screen.queryByText('Review & confirm')).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText(/pension account name/i), { target: { value: 'Fund' } });
  for (const weight of screen.getAllByRole('spinbutton').slice(-12)) fireEvent.change(weight, { target: { value: '0' } });
  await user.click(screen.getByRole('button', { name: /^next$/i }));
  await waitFor(() => expect(screen.getAllByRole('alert').some((alert) => /positive total/i.test(alert.textContent ?? ''))).toBe(true));
  expect(screen.queryByText('Review & confirm')).not.toBeInTheDocument();
});

test.each([
  ['negative', -1],
  ['fractional', 0.5],
] as const)('onboarding blocks %s credit weights at submit and never submits an invalid final payload', async (_label, invalidWeight) => {
  const user = userEvent.setup();
  let onboardingRequests = 0;
  server.use(http.post('/api/v1/onboarding', () => { onboardingRequests += 1; return HttpResponse.json({ ok: true }); }));
  render(<SetupPage />, { wrapper });
  await advanceToSalarySetup(user);
  await user.click(screen.getByLabelText(/configure pension/i));
  await user.type(screen.getByLabelText(/pension account name/i), 'Fund');
  fireEvent.change(screen.getByLabelText(/opening balance month/i), { target: { value: '2026-07-01' } });
  const firstWeight = screen.getByLabelText(/january setup weight/i);
  fireEvent.change(firstWeight, { target: { value: String(invalidWeight) } });
  const form = screen.getByLabelText(/pension account name/i).closest('form');
  expect(form).not.toBeNull();
  fireEvent.submit(form!); // Deliberately bypass native min/step constraint reporting.
  await waitFor(() => expect(screen.getAllByRole('alert').some((alert) => /twelve nonnegative integer weights with a positive total/i.test(alert.textContent ?? ''))).toBe(true));
  expect(screen.getByText('Step 7 of 8')).toBeInTheDocument();
  expect(screen.queryByText('Review & confirm')).not.toBeInTheDocument();
  expect(onboardingRequests).toBe(0);
});

test('unsupported onboarding percentage precision blocks preview and submit', async () => {
  const user = userEvent.setup();
  let previewRequests = 0;
  let onboardingRequests = 0;
  server.use(
    http.post('/api/v1/salary/calculate', () => { previewRequests += 1; return HttpResponse.json({}); }),
    http.post('/api/v1/onboarding', () => { onboardingRequests += 1; return HttpResponse.json({ ok: true }); }),
  );
  render(<SetupPage />, { wrapper });
  await advanceToSalarySetup(user);
  await user.click(screen.getByLabelText(/configure salary/i));
  fireEvent.change(screen.getByLabelText(/regional tax rate/i), { target: { value: '0.001' } });
  fireEvent.change(screen.getByLabelText(/ral/i), { target: { value: '50000' } });
  expect(await screen.findByRole('alert')).toHaveTextContent(/at most two decimal places/i);
  expect(previewRequests).toBe(0);
  const form = screen.getByLabelText(/ral/i).closest('form');
  expect(form).not.toBeNull();
  fireEvent.submit(form!);
  await waitFor(() => expect(screen.getAllByRole('alert').some((alert) => /tax rates from 0–100% with at most two decimal places/i.test(alert.textContent ?? ''))).toBe(true));
  expect(screen.getByText('Step 7 of 8')).toBeInTheDocument();
  expect(onboardingRequests).toBe(0);
});

test('salary and pension setup drafts survive Back from review without submission', async () => {
  const user = userEvent.setup();
  render(<SetupPage />, { wrapper });
  await advanceToSalarySetup(user);
  await user.click(screen.getByLabelText(/configure salary/i));
  fireEvent.change(screen.getByLabelText(/ral/i), { target: { value: '63000' } });
  fireEvent.change(screen.getByLabelText(/regional tax rate/i), { target: { value: '0.07' } });
  await user.click(screen.getByLabelText(/configure pension/i));
  fireEvent.change(screen.getByLabelText(/pension account name/i), { target: { value: 'Draft Fund' } });
  fireEvent.change(screen.getByLabelText(/at start of month/i), { target: { value: '2468' } });
  fireEvent.change(screen.getByLabelText(/opening balance month/i), { target: { value: '2026-08-17' } });
  fireEvent.change(screen.getByLabelText(/employee contribution rate/i), { target: { value: '0.07' } });
  fireEvent.change(screen.getByLabelText(/employee annual base/i), { target: { value: '12345' } });
  await user.selectOptions(screen.getByLabelText(/setup credit calendar preset/i), 'quarterly');
  await user.click(screen.getByRole('button', { name: /back/i }));
  await screen.findByText('Investment accounts (optional)');
  await user.click(screen.getByRole('button', { name: /next/i }));
  await screen.findByText('Optional salary and pension setup');
  expect(screen.getByLabelText(/configure salary/i)).toBeChecked();
  expect(screen.getByLabelText(/ral/i)).toHaveValue(63000);
  expect(screen.getByLabelText(/regional tax rate/i)).toHaveValue(0.07);
  expect(screen.getByLabelText(/configure pension/i)).toBeChecked();
  expect(screen.getByLabelText(/pension account name/i)).toHaveValue('Draft Fund');
  expect(screen.getByLabelText(/at start of month/i)).toHaveValue(2468);
  expect(screen.getByLabelText(/opening balance month/i)).toHaveValue('2026-08-17');
  expect(screen.getByLabelText(/employee contribution rate/i)).toHaveValue(0.07);
  expect(screen.getByLabelText(/employee annual base/i)).toHaveValue(12345);
  expect(screen.getByLabelText(/setup credit calendar preset/i)).toHaveValue('quarterly');
  expect(screen.getByLabelText(/march setup weight/i)).toHaveValue(1);
});

test('editing an already-reviewed salary and pension draft survives another Back/Next with incomplete raw values', async () => {
  const user = userEvent.setup();
  let onboardingRequests = 0;
  server.use(http.post('/api/v1/onboarding', () => { onboardingRequests += 1; return HttpResponse.json({ ok: true }); }));
  render(<SetupPage />, { wrapper });
  await advanceToSalarySetup(user);
  await user.click(screen.getByLabelText(/configure salary/i));
  fireEvent.change(screen.getByLabelText(/ral/i), { target: { value: '63000' } });
  fireEvent.change(screen.getByLabelText(/manual net override/i), { target: { value: '3100' } });
  await user.click(screen.getByLabelText(/configure pension/i));
  fireEvent.change(screen.getByLabelText(/pension account name/i), { target: { value: 'Original Fund' } });
  fireEvent.change(screen.getByLabelText(/at start of month/i), { target: { value: '1200' } });
  fireEvent.change(screen.getByLabelText(/opening balance month/i), { target: { value: '2026-07-01' } });
  await user.click(screen.getByRole('button', { name: /^next$/i }));
  await screen.findByText('Review & confirm');
  await user.click(screen.getByRole('button', { name: /back/i }));
  await screen.findByText('Optional salary and pension setup');

  fireEvent.change(screen.getByLabelText(/ral/i), { target: { value: '' } });
  fireEvent.change(screen.getByLabelText(/regional tax rate/i), { target: { value: '2.01' } });
  fireEvent.change(screen.getByLabelText(/manual net override/i), { target: { value: '3210' } });
  fireEvent.change(screen.getByLabelText(/pension account name/i), { target: { value: 'Latest Fund Draft' } });
  fireEvent.change(screen.getByLabelText(/at start of month/i), { target: { value: '4321' } });
  fireEvent.change(screen.getByLabelText(/opening balance month/i), { target: { value: '2026-08-19' } });
  fireEvent.change(screen.getByLabelText(/employee contribution rate/i), { target: { value: '0.07' } });
  fireEvent.change(screen.getByLabelText(/employee annual base/i), { target: { value: '23456' } });
  fireEvent.change(screen.getByLabelText(/employer contribution rate/i), { target: { value: '2.01' } });
  fireEvent.change(screen.getByLabelText(/employer annual base/i), { target: { value: '34567' } });
  fireEvent.change(screen.getByLabelText(/annual TFR contribution/i), { target: { value: '4567' } });
  await user.selectOptions(screen.getByLabelText(/setup credit calendar preset/i), 'quarterly');
  fireEvent.change(screen.getByLabelText(/january setup weight/i), { target: { value: '2' } });
  expect(screen.getByLabelText(/setup credit calendar preset/i)).toHaveValue('custom');
  const form = screen.getByLabelText(/pension account name/i).closest('form');
  expect(form).not.toBeNull();
  fireEvent.submit(form!);
  expect(await screen.findByRole('alert')).toHaveTextContent(/positive RAL/i);
  expect(screen.getByText('Step 7 of 8')).toBeInTheDocument();
  expect(screen.queryByText('Review & confirm')).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: /back/i }));
  await screen.findByText('Investment accounts (optional)');
  await user.click(screen.getByRole('button', { name: /next/i }));
  await screen.findByText('Optional salary and pension setup');

  expect(screen.getByLabelText(/configure salary/i)).toBeChecked();
  expect(screen.getByLabelText(/configure pension/i)).toBeChecked();
  expect((screen.getByLabelText(/ral/i) as HTMLInputElement).value).toBe('');
  expect(screen.getByLabelText(/regional tax rate/i)).toHaveValue(2.01);
  expect(screen.getByLabelText(/manual net override/i)).toHaveValue(3210);
  expect(screen.getByLabelText(/pension account name/i)).toHaveValue('Latest Fund Draft');
  expect(screen.getByLabelText(/at start of month/i)).toHaveValue(4321);
  expect(screen.getByLabelText(/opening balance month/i)).toHaveValue('2026-08-19');
  expect(screen.getByLabelText(/employee contribution rate/i)).toHaveValue(0.07);
  expect(screen.getByLabelText(/employee annual base/i)).toHaveValue(23456);
  expect(screen.getByLabelText(/employer contribution rate/i)).toHaveValue(2.01);
  expect(screen.getByLabelText(/employer annual base/i)).toHaveValue(34567);
  expect(screen.getByLabelText(/annual TFR contribution/i)).toHaveValue(4567);
  expect(screen.getByLabelText(/setup credit calendar preset/i)).toHaveValue('custom');
  expect(screen.getByLabelText(/january setup weight/i)).toHaveValue(2);
  expect(onboardingRequests).toBe(0);
});

test('disabling salary keeps a delivered late preview hidden after query observer notifications flush', async () => {
  const user = userEvent.setup();
  let resolvePreview!: (data: Awaited<ReturnType<typeof salaryApi.calculate>>) => void;
  const lateResponse = new Promise<Awaited<ReturnType<typeof salaryApi.calculate>>>((resolve) => { resolvePreview = resolve; });
  const lateResult = { computed_net_monthly: 2500, salary_months: 12, pension_deductibility_cap: 5300, tax_config_valid_from: '2026-01-01', pension_payroll_deduction_annual: 0 } as unknown as Awaited<ReturnType<typeof salaryApi.calculate>>;
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const calculate = vi.spyOn(salaryApi, 'calculate').mockImplementation(() => lateResponse);
  const localWrapper = ({ children }: { children: React.ReactNode }) => <QueryClientProvider client={queryClient}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>;
  render(<SetupPage />, { wrapper: localWrapper });
  await advanceToSalarySetup(user);
  const salaryToggle = screen.getByLabelText(/configure salary/i);
  await user.click(salaryToggle);
  await user.type(screen.getByLabelText(/ral/i), '30000');
  await waitFor(() => {
    const lastCall = calculate.mock.calls[calculate.mock.calls.length - 1];
    expect(lastCall?.[0].salary.ral).toBe(30000);
  });
  const finalCall = calculate.mock.calls[calculate.mock.calls.length - 1];
  expect(finalCall?.[0].salary.ral).toBe(30000);
  if (!finalCall) throw new Error('Final salary preview request was not observed.');
  const finalPreviewKey = queryKeys.salary.calculate(finalCall[0]);
  const finalPreviewQuery = queryClient.getQueryCache().find({ queryKey: finalPreviewKey, exact: true });
  if (!finalPreviewQuery) throw new Error('Final salary preview query was not created.');
  expect(finalPreviewQuery.getObserversCount()).toBeGreaterThan(0);
  expect(finalPreviewQuery.state.status).toBe('pending');
  expect(finalPreviewQuery.state.data).toBeUndefined();

  let resolveDelivered!: () => void;
  const delivered = new Promise<void>((resolve) => { resolveDelivered = resolve; });
  const unsubscribe = queryClient.getQueryCache().subscribe((event) => {
    if (event.type === 'updated' && event.query === finalPreviewQuery && event.query.state.status === 'success' && event.query.state.data === lateResult) resolveDelivered();
  });
  await user.click(salaryToggle);
  expect(finalPreviewQuery.getObserversCount()).toBeGreaterThan(0);
  expect(finalPreviewQuery.state.data).toBeUndefined();
  await act(async () => {
    resolvePreview(lateResult);
    await lateResponse;
    await delivered;
    await new Promise<void>((resolve) => setTimeout(resolve, 0));
  });
  expect(finalPreviewQuery.state.status).toBe('success');
  expect(finalPreviewQuery.state.data).toBe(lateResult);
  expect(screen.queryByText(/Backend estimate/)).not.toBeInTheDocument();
  expect(screen.queryByText(/Could not preview salary/)).not.toBeInTheDocument();
  unsubscribe();
  calculate.mockRestore();
});

test('disabling salary hides an already-visible cached preview and final onboarding omits salary', async () => {
  const user = userEvent.setup();
  let previewRequest: any;
  let submitted: any;
  server.use(
    http.post('/api/v1/salary/calculate', async ({ request }) => {
      previewRequest = await request.json();
      return HttpResponse.json({ gross_annual: 30000, social_security: 0, employee_pension_contribution_annual: 0, employer_pension_contribution_annual: 0, tfr_contribution_annual: 0, pension_payroll_deduction_annual: 0, pension_employer_taxable_excess_annual: 0, pension_cap_eligible_contributions_annual: 0, pension_cap_used_annual: 0, pension_cap_excess_annual: 0, pension_deductibility_cap: 5300, pension_cap_scope: 'Configured payroll', tax_config_id: 'tax', tax_config_valid_from: '2026-01-01', taxable_base: 30000, income_tax_gross: 0, employment_deduction: 0, income_tax_net: 0, regional_surtax: 0, municipal_surtax: 0, net_annual: 30000, computed_net_monthly: 2500, meal_vouchers_monthly: 0, welfare_monthly: 0, salary_months: 12 });
    }),
    http.post('/api/v1/onboarding', async ({ request }) => { submitted = await request.json(); return HttpResponse.json({ ok: true }); }),
  );
  render(<SetupPage />, { wrapper });
  await advanceToSalarySetup(user);
  const salaryToggle = screen.getByLabelText(/configure salary/i);
  await user.click(salaryToggle);
  await user.type(screen.getByLabelText(/ral/i), '30000');
  expect(await screen.findByText(/Backend estimate at 2026-07-01/)).toBeInTheDocument();
  expect(previewRequest.salary.ral).toBe(30000);
  await user.click(salaryToggle);
  expect(screen.queryByText(/Backend estimate/)).not.toBeInTheDocument();
  expect(screen.queryByText(/Could not preview salary/)).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: /^next$/i }));
  expect((await screen.findByText(/^Salary:$/)).parentElement).toHaveTextContent('not configured');
  await user.click(screen.getByRole('button', { name: /confirm & start/i }));
  await waitFor(() => expect(submitted).toBeTruthy());
  expect(submitted.salary).toBeUndefined();
});

test('Back navigation preserves a valid linked bank-funded payment method', async () => {
  const user = userEvent.setup();
  render(<SetupPage />, { wrapper });

  // Step 1: start date
  fireEvent.change(screen.getByLabelText(/tracking start month/i), { target: { value: '2026-01-01' } });
  await user.click(screen.getByRole('button', { name: /next/i }));

  // Step 2: main bank
  await waitFor(() => expect(screen.getByText('Main bank account')).toBeInTheDocument());
  await user.type(screen.getByLabelText(/account name/i), 'Main Bank');
  await user.type(screen.getByLabelText(/current balance/i), '1000');
  await user.click(screen.getByRole('button', { name: /next/i }));

  // Step 3: additional banks (optional, skip straight through)
  await waitFor(() =>
    expect(screen.getByText('Additional bank accounts (optional)')).toBeInTheDocument()
  );
  await user.click(screen.getByRole('button', { name: /next/i }));

  // Step 4: payment methods — bank-funded cards require an owned onboarding bank.
  await waitFor(() => expect(screen.getByText('Payment methods (optional)')).toBeInTheDocument());
  await user.type(screen.getByLabelText(/^name$/i), 'My Card');
  await user.click(screen.getByRole('button', { name: /^add$/i }));
  expect(screen.queryByText('My Card')).not.toBeInTheDocument();

  await user.type(screen.getByLabelText(/linked bank/i), 'Main Bank');
  await user.click(screen.getByRole('button', { name: /^add$/i }));
  expect(screen.getByText('My Card')).toBeInTheDocument();

  // Advance to step 5, then go Back to step 4
  await user.click(screen.getByRole('button', { name: /next/i }));
  await waitFor(() => expect(screen.getByText('Saving accounts (optional)')).toBeInTheDocument());
  await user.click(screen.getByRole('button', { name: /back/i }));

  // The step remounts — entry must still be rendered (rehydrated from context)
  await waitFor(() => expect(screen.getByText('Payment methods (optional)')).toBeInTheDocument());
  expect(screen.getByText('My Card')).toBeInTheDocument();

  // Continue forward through the rest of the wizard to the review screen
  await user.click(screen.getByRole('button', { name: /next/i }));
  await waitFor(() => expect(screen.getByText('Saving accounts (optional)')).toBeInTheDocument());
  await user.click(screen.getByRole('button', { name: /next/i }));
  await waitFor(() =>
    expect(screen.getByText('Investment accounts (optional)')).toBeInTheDocument()
  );
  await user.click(screen.getByRole('button', { name: /next/i }));
  await waitFor(() =>
    expect(screen.getByText('Optional salary and pension setup')).toBeInTheDocument()
  );
  await user.click(screen.getByRole('button', { name: /skip/i }));

  // Review screen must count the payment method that survived the Back/Next round trip
  await waitFor(() => expect(screen.getByText('Review & confirm')).toBeInTheDocument());
  expect(screen.getByText(/Payment methods:/).parentElement).toHaveTextContent('Payment methods: 1');
});

// ---------------------------------------------------------------------------
// Tests: SetupGuard redirect for already-onboarded users
// ---------------------------------------------------------------------------

// SetupGuard is not exported directly; we reproduce its behaviour by rendering
// the guarded route tree with MemoryRouter starting at /setup.
// When onboarding is complete the guard redirects to /, so we assert that
// the home placeholder renders instead of the setup wizard.

// Import the guard from the router module so we don't duplicate logic.
// The router module exports createRouter but not SetupGuard individually.
// Instead we inline a thin reproduction that mirrors the real guard exactly.
import { useQuery } from '@tanstack/react-query';
import { Navigate } from 'react-router-dom';
import { onboardingApi } from '../../src/api/onboarding';
import { fetchMeOrNull } from '../../src/api/auth';

function TestSetupGuard() {
  const { data: user, isLoading } = useQuery({
    queryKey: ['auth', 'me'],
    queryFn: fetchMeOrNull,
    retry: false,
    staleTime: 30_000,
  });
  const { data: status, isLoading: statusLoading } = useQuery({
    queryKey: ['onboarding', 'status'],
    queryFn: onboardingApi.status,
    enabled: !!user,
    retry: false,
    staleTime: 30_000,
  });

  if (isLoading || (user && statusLoading)) return null;
  if (user && status?.complete) return <Navigate to="/" replace />;
  return <Outlet />;
}

test('SetupGuard redirects to "/" when onboarding is already complete', async () => {
  // Override the default handler so onboarding is complete
  server.use(
    http.get('/api/v1/onboarding/status', () =>
      HttpResponse.json({ complete: true })
    )
  );

  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });

  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/setup']}>
        <Routes>
          <Route element={<TestSetupGuard />}>
            <Route path="/setup" element={<div>Setup wizard</div>} />
          </Route>
          <Route path="/" element={<div>Home dashboard</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );

  // After queries resolve the guard redirects to "/" — wait for the home content
  await waitFor(() =>
    expect(screen.getByText('Home dashboard')).toBeInTheDocument()
  );
  expect(screen.queryByText('Setup wizard')).not.toBeInTheDocument();
});

test('SetupGuard shows setup page when onboarding is not complete', async () => {
  server.use(
    http.get('/api/v1/onboarding/status', () =>
      HttpResponse.json({ complete: false })
    )
  );

  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });

  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/setup']}>
        <Routes>
          <Route element={<TestSetupGuard />}>
            <Route path="/setup" element={<div>Setup wizard</div>} />
          </Route>
          <Route path="/" element={<div>Home dashboard</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );

  await waitFor(() =>
    expect(screen.getByText('Setup wizard')).toBeInTheDocument()
  );
  expect(screen.queryByText('Home dashboard')).not.toBeInTheDocument();
});
