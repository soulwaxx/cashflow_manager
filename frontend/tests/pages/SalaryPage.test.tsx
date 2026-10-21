import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';
import SalaryPage from '../../src/pages/SalaryPage';
import TransferForm from '../../src/components/transfers/TransferForm';

const salary = { id: 's1', user_id: 'u1', valid_from: '2025-01-01', ral: 42000, regional_tax_rate: .0173, municipal_tax_rate: .001, meal_vouchers_annual: 0, welfare_annual: 0, salary_months: 13, manual_net_override: 2800, computed_net_monthly: 2700, effective_net_monthly: 2800, calculated_as_of: '2025-01-01', salary_config_id: 's1', salary_config_valid_from: '2025-01-01', pension_config_id: 'p1', pension_config_valid_from: '2025-01-01', pension: { employee_pension_contribution_annual: 300, employer_pension_contribution_annual: 800, tfr_contribution_annual: 0, pension_payroll_deduction_annual: 300, pension_employer_taxable_excess_annual: 0, pension_cap_eligible_contributions_annual: 1100, pension_cap_used_annual: 1100, pension_cap_excess_annual: 0, pension_deductibility_cap: 5164.57, pension_cap_scope: 'Configured ordinary payroll contributions only' }, tax_config_id: 't1', tax_config_valid_from: '2025-01-01' };
const breakdown = { gross_annual: 42000, social_security: 4000, employee_pension_contribution_annual: 300, employer_pension_contribution_annual: 800, tfr_contribution_annual: 0, pension_payroll_deduction_annual: 300, pension_employer_taxable_excess_annual: 0, pension_cap_eligible_contributions_annual: 1100, pension_cap_used_annual: 1100, pension_cap_excess_annual: 0, pension_deductibility_cap: 5164.57, pension_cap_scope: 'Configured ordinary payroll contributions only', tax_config_id: 't1', tax_config_valid_from: '2025-01-01', taxable_base: 38000, income_tax_gross: 8000, employment_deduction: 1000, income_tax_net: 7000, regional_surtax: 500, municipal_surtax: 40, net_annual: 30500, computed_net_monthly: 2346.15, meal_vouchers_monthly: 0, welfare_monthly: 0, salary_months: 13, calculated_as_of: '2025-01-01', salary_config_id: 's1', salary_config_valid_from: '2025-01-01', pension_config_id: 'p1', pension_config_valid_from: '2025-01-01', manual_net_override: 2800, effective_net_monthly: 2800 };

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>;
}

beforeEach(() => server.use(
  http.get('/api/v1/salary', () => HttpResponse.json([salary])),
  http.get('/api/v1/pension/configs', () => HttpResponse.json([{ id: 'p1', user_id: 'u1', account_id: 'fund1', valid_from: '2025-01-01', employee_contrib_rate: .01, employee_contrib_annual_base: 30000, employer_contrib_rate: .02, employer_contrib_annual_base: 40000, tfr_contrib_annual: 0, contribution_periods_by_month: Array(12).fill(1) }])),
  http.get('/api/v1/accounts', () => HttpResponse.json([{ id: 'fund1', user_id: 'u1', type: 'pension', name: 'Fund', opening_balance: 0, opening_balance_month: '2025-01-01', is_active: true }])),
  http.get('/api/v1/salary/breakdown', () => HttpResponse.json(breakdown)),
));

test('renders salary and independent pension period sections and backend historical cap', async () => {
  render(<SalaryPage />, { wrapper });
  expect(await screen.findByText('Salary effective periods')).toBeInTheDocument();
  expect(screen.getByText('Pension effective periods')).toBeInTheDocument();
  expect(await screen.findByText(/cap effective 2025-01-01/i)).toBeInTheDocument();
  expect(screen.getByText(/5164,57|5\.164,57/)).toBeInTheDocument();
  expect(screen.getByText(/Average net per salary payment \(13\/year\)/)).toBeInTheDocument();
  expect(screen.getByText(/Manual override €2\.800,00/)).toBeInTheDocument();
});

test('pension period form uses explicit owned account and monthly/quarterly integer calendar presets', async () => {
  const user = userEvent.setup();
  let posted: any;
  server.use(http.post('/api/v1/pension/configs', async ({ request }) => {
    posted = await request.json();
    return HttpResponse.json({ id: 'p2', ...posted, user_id: 'u1' }, { status: 201 });
  }));
  render(<SalaryPage />, { wrapper });
  await user.click(await screen.findByRole('button', { name: /add pension period/i }));
  const dialog = screen.getByRole('dialog');
  await user.type(within(dialog).getByLabelText(/effective from/i), '2026-04-01');
  await user.selectOptions(within(dialog).getByLabelText(/active owned pension account/i), 'fund1');
  await user.selectOptions(within(dialog).getByLabelText(/credit calendar preset/i), 'quarterly');
  await user.clear(within(dialog).getByLabelText(/employee contribution rate/i));
  await user.type(within(dialog).getByLabelText(/employee contribution rate/i), '0.07');
  await user.click(within(dialog).getByRole('button', { name: /save pension period/i }));
  await waitFor(() => expect(posted).toBeTruthy());
  expect(posted).toMatchObject({ account_id: 'fund1', valid_from: '2026-04-01', employee_contrib_rate: 0.0007, employee_contrib_annual_base: 0, employer_contrib_rate: 0, employer_contrib_annual_base: 0, tfr_contrib_annual: 0, contribution_periods_by_month: [0,0,1,0,0,1,0,0,1,0,0,1] });
});

test('existing pension period edits serialize precise nonzero contribution rates', async () => {
  const user = userEvent.setup();
  let updated: any;
  server.use(http.put('/api/v1/pension/configs/p1', async ({ request }) => { updated = await request.json(); return HttpResponse.json({ id: 'p1', user_id: 'u1', ...updated }); }));
  render(<SalaryPage />, { wrapper });
  await user.click((await screen.findAllByRole('button', { name: /^edit$/i }))[1]);
  const dialog = screen.getByRole('dialog');
  await user.clear(within(dialog).getByLabelText(/employee contribution rate/i));
  await user.type(within(dialog).getByLabelText(/employee contribution rate/i), '0.07');
  await user.clear(within(dialog).getByLabelText(/employer contribution rate/i));
  await user.type(within(dialog).getByLabelText(/employer contribution rate/i), '2.01');
  await user.click(within(dialog).getByRole('button', { name: /save pension period/i }));
  await waitFor(() => expect(updated).toBeTruthy());
  expect(updated.employee_contrib_rate).toBe(0.0007);
  expect(updated.employer_contrib_rate).toBe(0.0201);
});

test('existing pension period can change its effective month and custom integer weights', async () => {
  const user = userEvent.setup();
  let updated: any;
  server.use(http.put('/api/v1/pension/configs/p1', async ({ request }) => { updated = await request.json(); return HttpResponse.json({ id: 'p1', user_id: 'u1', ...updated }); }));
  render(<SalaryPage />, { wrapper });
  await user.click((await screen.findAllByRole('button', { name: /^edit$/i }))[1]);
  const dialog = screen.getByRole('dialog');
  fireEvent.change(within(dialog).getByLabelText(/effective from/i), { target: { value: '2025-02-01' } });
  await user.selectOptions(within(dialog).getByLabelText(/credit calendar preset/i), 'monthly');
  fireEvent.change(within(dialog).getByLabelText(/january credit weight/i), { target: { value: '2' } });
  await user.click(within(dialog).getByRole('button', { name: /save pension period/i }));
  await waitFor(() => expect(updated).toBeTruthy());
  expect(updated.valid_from).toBe('2025-02-01');
  expect(updated.contribution_periods_by_month).toEqual([2,1,1,1,1,1,1,1,1,1,1,1]);
});

test('clearing manual override sends explicit null and preserves effective-month identity', async () => {
  const user = userEvent.setup();
  let updated: any;
  server.use(http.put('/api/v1/salary/s1', async ({ request }) => { updated = await request.json(); return HttpResponse.json({ ...salary, ...updated, manual_net_override: null }); }));
  render(<SalaryPage />, { wrapper });
  await user.click((await screen.findAllByRole('button', { name: /^edit$/i }))[0]);
  const dialog = screen.getByRole('dialog');
  await user.clear(within(dialog).getByLabelText(/manual net override/i));
  await user.click(within(dialog).getByRole('button', { name: /save salary period/i }));
  await waitFor(() => expect(updated).toBeTruthy());
  expect(updated).toMatchObject({ valid_from: '2025-01-01', manual_net_override: null });
});

test('salary percentage inputs serialize as exact four-decimal fractions', async () => {
  const user = userEvent.setup();
  let posted: any;
  server.use(http.post('/api/v1/salary', async ({ request }) => { posted = await request.json(); return HttpResponse.json({ id: 's2', user_id: 'u1', ...posted }, { status: 201 }); }));
  render(<SalaryPage />, { wrapper });
  await user.click(await screen.findByRole('button', { name: /add salary period/i }));
  const dialog = screen.getByRole('dialog');
  fireEvent.change(within(dialog).getByLabelText(/effective from/i), { target: { value: '2026-10-01' } });
  await user.type(within(dialog).getByLabelText(/ral/i), '50000');
  fireEvent.change(within(dialog).getByLabelText(/regional tax rate/i), { target: { value: '0.07' } });
  await user.click(within(dialog).getByRole('button', { name: /save salary period/i }));
  await waitFor(() => expect(posted).toBeTruthy());
  expect(posted).toMatchObject({ regional_tax_rate: 0.0007, municipal_tax_rate: 0.001 });
});

test('unsupported pension percentage precision is rejected before saving', async () => {
  const user = userEvent.setup();
  let posted: unknown;
  server.use(http.post('/api/v1/pension/configs', async ({ request }) => { posted = await request.json(); return HttpResponse.json({ id: 'p2' }, { status: 201 }); }));
  render(<SalaryPage />, { wrapper });
  await user.click(await screen.findByRole('button', { name: /add pension period/i }));
  const dialog = screen.getByRole('dialog');
  await user.type(within(dialog).getByLabelText(/effective from/i), '2026-10-01');
  await user.selectOptions(within(dialog).getByLabelText(/active owned pension account/i), 'fund1');
  await user.type(within(dialog).getByLabelText(/employee contribution rate/i), '0.001');
  await user.click(within(dialog).getByRole('button', { name: /save pension period/i }));
  expect(await within(dialog).findByRole('alert')).toHaveTextContent(/at most two decimal places/i);
  expect(posted).toBeUndefined();
});

test('all-zero custom calendar is rejected accessibly before saving', async () => {
  const user = userEvent.setup();
  render(<SalaryPage />, { wrapper });
  await user.click(await screen.findByRole('button', { name: /add pension period/i }));
  const dialog = screen.getByRole('dialog');
  await user.type(within(dialog).getByLabelText(/effective from/i), '2026-04-01');
  await user.selectOptions(within(dialog).getByLabelText(/active owned pension account/i), 'fund1');
  for (const weight of within(dialog).getAllByRole('spinbutton').slice(-12)) fireEvent.change(weight, { target: { value: '0' } });
  await user.click(within(dialog).getByRole('button', { name: /save pension period/i }));
  expect(await within(dialog).findByRole('alert')).toHaveTextContent(/positive total/i);
});

test('selected-month breakdown displays backend values and handles missing tax without a client fallback', async () => {
  server.use(http.get('/api/v1/salary/breakdown', () => HttpResponse.json({ detail: 'No tax config found for the given period' }, { status: 422 })));
  render(<SalaryPage />, { wrapper });
  expect(await screen.findByText(/No tax config found for the given period/i)).toBeInTheDocument();
  expect(screen.queryByText(/5300/)).not.toBeInTheDocument();
});

test('pension summary remains available when salary breakdown is unavailable', async () => {
  server.use(
    http.get('/api/v1/salary/breakdown', () => HttpResponse.json({ detail: 'No salary config' }, { status: 404 })),
    http.get('/api/v1/pension/summary', () => HttpResponse.json({ year: 2026, as_of: '2026-10-01', config: null, year_to_date: { employee: 0, employer: 0, tfr: 0 }, annualized: { employee: 1250, employer: 900, tfr: 400, eligible_contributions: 2150, cap_used: 2150, cap_excess: 0, cap: 5300, cap_scope: 'Configured contributions', tax_config_valid_from: '2026-01-01' } })),
  );
  render(<SalaryPage />, { wrapper });
  expect(await screen.findByText(/Annualized employee €1\.250,00/)).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: /Selected month pension summary/ })).toBeInTheDocument();
});

test.each([
  [400, 'Invalid pension amount'],
  [409, 'Effective period conflicts'],
  [422, [{ loc: ['body', 'ral'], msg: 'Input should be greater than zero', type: 'greater_than' }]],
] as const)('renders safely for HTTP %i validation detail', async (status, detail) => {
  const user = userEvent.setup();
  server.use(http.post('/api/v1/salary', () => HttpResponse.json({ detail }, { status })));
  render(<SalaryPage />, { wrapper });
  await user.click(await screen.findByRole('button', { name: /add salary period/i }));
  const dialog = screen.getByRole('dialog');
  fireEvent.change(within(dialog).getByLabelText(/effective from/i), { target: { value: '2026-10-01' } });
  await user.type(within(dialog).getByLabelText(/ral/i), '42000');
  await user.click(within(dialog).getByRole('button', { name: /save salary period/i }));
  const expectedMessage = typeof detail === 'string' ? detail : detail[0].msg;
  expect(await screen.findByRole('alert')).toHaveTextContent(expectedMessage);
  expect(screen.getByRole('dialog')).toBeInTheDocument();
});

test.each([
  ['SalaryPage first', true],
  ['TransferForm first', false],
] as const)('shared account cache preserves pension filtering and transfer options (%s)', async (_label, salaryFirst) => {
  const allAccounts = [
    { id: 'fund1', user_id: 'u1', type: 'pension', name: 'Active Fund', opening_balance: 0, opening_balance_month: '2025-01-01', is_active: true },
    { id: 'oldfund', user_id: 'u1', type: 'pension', name: 'Inactive Fund', opening_balance: 0, opening_balance_month: '2025-01-01', is_active: false },
    { id: 'save1', user_id: 'u1', type: 'saving', name: 'Savings', opening_balance: 0, opening_balance_month: '2025-01-01', is_active: true },
    { id: 'invest1', user_id: 'u1', type: 'investment', name: 'Brokerage', opening_balance: 0, opening_balance_month: '2025-01-01', is_active: true },
  ];
  let accountRequests = 0;
  server.use(http.get('/api/v1/accounts', ({ request }) => {
    accountRequests += 1;
    const type = new URL(request.url).searchParams.get('type');
    return HttpResponse.json(type ? allAccounts.filter((account) => account.type === type) : allAccounts);
  }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 60_000 } } });
  const user = userEvent.setup();
  const first = salaryFirst ? <SalaryPage /> : <TransferForm onSuccess={() => undefined} />;
  const second = salaryFirst ? <TransferForm onSuccess={() => undefined} /> : <SalaryPage />;
  const view = render(<QueryClientProvider client={qc}><MemoryRouter>{first}</MemoryRouter></QueryClientProvider>);
  if (salaryFirst) {
    expect(await screen.findByText(/Account: Active Fund/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /add pension period/i }));
  } else {
    expect(await screen.findByLabelText(/from account type/i)).toBeInTheDocument();
  }
  view.rerender(<QueryClientProvider client={qc}><MemoryRouter><>{first}{second}</></MemoryRouter></QueryClientProvider>);
  const transferType = await screen.findByLabelText(/from account type/i);
  await user.selectOptions(transferType, 'saving');
  expect(screen.getAllByRole('option', { name: 'Savings' })).toHaveLength(2);
  await user.selectOptions(transferType, 'investment');
  await user.selectOptions(screen.getByLabelText(/to account type/i), 'investment');
  expect(screen.getAllByRole('option', { name: 'Brokerage' })).toHaveLength(2);
  await user.selectOptions(transferType, 'pension');
  await user.selectOptions(screen.getByLabelText(/to account type/i), 'pension');
  expect(screen.getAllByRole('option', { name: 'Inactive Fund' })).toHaveLength(2);
  if (!salaryFirst) await user.click(await screen.findByRole('button', { name: /add pension period/i }));
  const dialog = screen.getByRole('dialog');
  const accountSelect = within(dialog).getByLabelText(/active owned pension account/i);
  expect(Array.from((accountSelect as HTMLSelectElement).options).map((option) => option.textContent)).toEqual(['Choose an account', 'Active Fund']);
  expect(within(dialog).queryByRole('option', { name: 'Savings' })).not.toBeInTheDocument();
  expect(within(dialog).queryByRole('option', { name: 'Brokerage' })).not.toBeInTheDocument();
  expect(within(dialog).queryByRole('option', { name: 'Inactive Fund' })).not.toBeInTheDocument();
  expect(accountRequests).toBe(1);
});

test('historical pension summary is selected before the first salary period', async () => {
  let summaryParams = '';
  let breakdownRequests = 0;
  const historicalPension = { id: 'hp1', user_id: 'u1', account_id: 'fund1', valid_from: '2026-01-01', employee_contrib_rate: 0.0007, employee_contrib_annual_base: 14000, employer_contrib_rate: 0.0201, employer_contrib_annual_base: 18000, tfr_contrib_annual: 400, contribution_periods_by_month: Array(12).fill(1) };
  server.use(
    http.get('/api/v1/salary', () => HttpResponse.json([{ ...salary, valid_from: '2026-04-01' }])),
    http.get('/api/v1/pension/configs', () => HttpResponse.json([historicalPension])),
    http.get('/api/v1/pension/summary', ({ request }) => {
      const url = new URL(request.url);
      summaryParams = url.search;
      return HttpResponse.json({ year: Number(url.searchParams.get('year')), as_of: url.searchParams.get('as_of'), config: historicalPension, year_to_date: { employee: 321, employer: 654, tfr: 87 }, annualized: { employee: 98, employer: 765, tfr: 432, eligible_contributions: 1000, cap_used: 1000, cap_excess: 0, cap: 4321, cap_scope: 'Historical payroll scope', tax_config_valid_from: '2026-01-01' } });
    }),
    http.get('/api/v1/salary/breakdown', () => { breakdownRequests += 1; return HttpResponse.json(breakdown); }),
  );
  render(<SalaryPage />, { wrapper });
  fireEvent.change(screen.getByLabelText(/selected effective\/reporting month/i), { target: { value: '2026-02-19' } });
  await screen.findByRole('heading', { name: /Selected month pension summary · 2026-02-01/ });
  expect(await screen.findByText(/Annualized employee €98,00/)).toBeInTheDocument();
  expect(screen.getByText(/Historical payroll scope · tax cap effective 2026-01-01/)).toBeInTheDocument();
  expect(screen.getByText(/cap €4\.321,00/)).toBeInTheDocument();
  expect(summaryParams).toContain('year=2026');
  expect(summaryParams).toContain('as_of=2026-02-01');
  expect(screen.getByRole('status')).toHaveTextContent(/Pension period applies without a salary period/);
  expect(screen.queryByText(/Computed net\/payment/)).not.toBeInTheDocument();
  expect(breakdownRequests).toBe(0);
});

test('pension and account lookup failures are distinct from empty results and can retry', async () => {
  const user = userEvent.setup();
  let recovered = false;
  server.use(
    http.get('/api/v1/accounts', () => recovered ? HttpResponse.json([{ id: 'fund1', user_id: 'u1', type: 'pension', name: 'Fund', opening_balance: 0, opening_balance_month: '2025-01-01', is_active: true }]) : HttpResponse.json({ detail: 'Account service unavailable' }, { status: 503 })),
    http.get('/api/v1/pension/configs', () => recovered ? HttpResponse.json([]) : HttpResponse.json({ detail: 'Pension service unavailable' }, { status: 503 })),
  );
  render(<SalaryPage />, { wrapper });
  expect(await screen.findByText(/Could not load pension periods/)).toBeInTheDocument();
  expect(await screen.findByText(/Could not load account destinations/)).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: /add pension period/i }));
  const dialog = screen.getByRole('dialog');
  expect(within(dialog).getByLabelText(/active owned pension account/i)).toBeDisabled();
  recovered = true;
  await user.click(screen.getByRole('button', { name: /retry pension lookup/i }));
  await user.click(within(dialog).getByRole('button', { name: /retry accounts/i }));
  await waitFor(() => expect(screen.getByText('No pension period configured.')).toBeInTheDocument());
  expect(screen.queryByText(/Could not load pension periods/)).not.toBeInTheDocument();
  expect(screen.queryByText(/Could not load account destinations/)).not.toBeInTheDocument();
});

test('pension creation blocks loading and nonmember destinations, then saves an explicit recovered choice', async () => {
  const user = userEvent.setup();
  let resolveAccounts!: () => void;
  const accountsReady = new Promise<void>((resolve) => { resolveAccounts = resolve; });
  let markLookupStarted!: () => void;
  const lookupStarted = new Promise<void>((resolve) => { markLookupStarted = resolve; });
  let posted: any;
  let postCount = 0;
  const availableAccounts = [
    { id: 'fund1', user_id: 'u1', type: 'pension', name: 'Fund One', opening_balance: 0, opening_balance_month: '2025-01-01', is_active: true },
    { id: 'fund2', user_id: 'u1', type: 'pension', name: 'Fund Two', opening_balance: 0, opening_balance_month: '2025-01-01', is_active: true },
  ];
  server.use(
    http.get('/api/v1/accounts', async () => { markLookupStarted(); await accountsReady; return HttpResponse.json(availableAccounts); }),
    http.post('/api/v1/pension/configs', async ({ request }) => {
      postCount += 1;
      posted = await request.json();
      return HttpResponse.json({ id: 'p2', user_id: 'u1', ...posted }, { status: 201 });
    }),
  );
  render(<SalaryPage />, { wrapper });
  await lookupStarted;
  await user.click(screen.getByRole('button', { name: /add pension period/i }));
  const dialog = screen.getByRole('dialog');
  fireEvent.change(within(dialog).getByLabelText(/effective from/i), { target: { value: '2026-10-01' } });
  const accountSelect = within(dialog).getByLabelText(/active owned pension account/i);
  const save = within(dialog).getByRole('button', { name: /save pension period/i });
  const form = accountSelect.closest('form');
  expect(form).not.toBeNull();
  expect(save).toBeDisabled();
  fireEvent.submit(form!);
  expect(postCount).toBe(0);

  resolveAccounts();
  await waitFor(() => expect(accountSelect).not.toBeDisabled());
  expect(save).toBeDisabled();
  fireEvent.change(accountSelect, { target: { value: 'not-offered' } });
  expect(save).toBeDisabled();
  fireEvent.submit(form!);
  expect(postCount).toBe(0);

  await user.selectOptions(accountSelect, 'fund1');
  expect(save).toBeEnabled();
  await user.click(save);
  await waitFor(() => expect(postCount).toBe(1));
  expect(posted).toMatchObject({ account_id: 'fund1', valid_from: '2026-10-01' });
});

test('pension creation blocks direct form submission when lookup succeeds with no destinations', async () => {
  const user = userEvent.setup();
  let postCount = 0;
  server.use(
    http.get('/api/v1/accounts', () => HttpResponse.json([])),
    http.post('/api/v1/pension/configs', () => { postCount += 1; return HttpResponse.json({ id: 'p2' }, { status: 201 }); }),
  );
  render(<SalaryPage />, { wrapper });
  await user.click(await screen.findByRole('button', { name: /add pension period/i }));
  const dialog = screen.getByRole('dialog');
  fireEvent.change(within(dialog).getByLabelText(/effective from/i), { target: { value: '2026-10-01' } });
  expect(await within(dialog).findByText(/No active owned pension accounts are available/)).toBeInTheDocument();
  const accountSelect = within(dialog).getByLabelText(/active owned pension account/i);
  const save = within(dialog).getByRole('button', { name: /save pension period/i });
  const form = accountSelect.closest('form');
  expect(form).not.toBeNull();
  expect(accountSelect).toBeDisabled();
  expect(save).toBeDisabled();
  fireEvent.submit(form!);
  expect(postCount).toBe(0);
});

test('editing a salary period beyond the selected month hides its cached breakdown', async () => {
  const user = userEvent.setup();
  let effectiveFrom = '2026-01-01';
  server.use(
    http.get('/api/v1/salary', () => HttpResponse.json([{ ...salary, valid_from: effectiveFrom }])),
    http.get('/api/v1/pension/configs', () => HttpResponse.json([])),
    http.put('/api/v1/salary/s1', async ({ request }) => {
      const body = await request.json() as { valid_from: string };
      effectiveFrom = body.valid_from;
      return HttpResponse.json({ ...salary, ...body });
    }),
  );
  render(<SalaryPage />, { wrapper });
  fireEvent.change(screen.getByLabelText(/selected effective\/reporting month/i), { target: { value: '2026-03-01' } });
  expect(await screen.findByText(/Computed net annual €30\.500,00/)).toBeInTheDocument();

  await user.click((await screen.findAllByRole('button', { name: /^edit$/i }))[0]);
  const dialog = screen.getByRole('dialog');
  fireEvent.change(within(dialog).getByLabelText(/effective from/i), { target: { value: '2026-04-01' } });
  await user.click(within(dialog).getByRole('button', { name: /save salary period/i }));

  expect(await screen.findByRole('status')).toHaveTextContent(/No salary period applies to this month/i);
  expect(screen.queryByText(/Computed net annual/)).not.toBeInTheDocument();
  expect(screen.queryByText(/Gross annual/)).not.toBeInTheDocument();
});

test.each([
  [404, 'No salary config'],
  [422, 'No tax config found for the given period'],
] as const)('a failed selected-month breakdown refetch (%i) hides cached financial values and shows its error', async (status, detail) => {
  let failMarch = false;
  server.use(http.get('/api/v1/salary/breakdown', ({ request }) => {
    if (new URL(request.url).searchParams.get('as_of') === '2026-03-01' && failMarch) {
      return HttpResponse.json({ detail }, { status });
    }
    return HttpResponse.json(breakdown);
  }));
  render(<SalaryPage />, { wrapper });
  const monthInput = screen.getByLabelText(/selected effective\/reporting month/i);
  fireEvent.change(monthInput, { target: { value: '2026-03-01' } });
  expect(await screen.findByText(/Computed net annual €30\.500,00/)).toBeInTheDocument();

  fireEvent.change(monthInput, { target: { value: '2026-04-01' } });
  expect(await screen.findByText(/Computed net annual €30\.500,00/)).toBeInTheDocument();
  failMarch = true;
  fireEvent.change(monthInput, { target: { value: '2026-03-01' } });

  expect(await screen.findByRole('status')).toHaveTextContent(detail);
  expect(screen.queryByText(/Computed net annual/)).not.toBeInTheDocument();
  expect(screen.queryByText(/Gross annual/)).not.toBeInTheDocument();
});

test('pension edit preserves its destination through lookup failure and updates only after recovery', async () => {
  const user = userEvent.setup();
  let recovered = false;
  let updated: any;
  let updateCount = 0;
  server.use(
    http.get('/api/v1/accounts', () => recovered ? HttpResponse.json([
      { id: 'fund1', user_id: 'u1', type: 'pension', name: 'Original Fund', opening_balance: 0, opening_balance_month: '2025-01-01', is_active: true },
      { id: 'fund2', user_id: 'u1', type: 'pension', name: 'Other Fund', opening_balance: 0, opening_balance_month: '2025-01-01', is_active: true },
    ]) : HttpResponse.json({ detail: 'Account service unavailable' }, { status: 503 })),
    http.put('/api/v1/pension/configs/p1', async ({ request }) => {
      updateCount += 1;
      updated = await request.json();
      return HttpResponse.json({ id: 'p1', user_id: 'u1', ...updated });
    }),
  );
  render(<SalaryPage />, { wrapper });
  expect(await screen.findByText(/Could not load account destinations/)).toBeInTheDocument();
  await user.click((await screen.findAllByRole('button', { name: /^edit$/i }))[1]);
  const dialog = screen.getByRole('dialog');
  const accountSelect = within(dialog).getByLabelText(/active owned pension account/i);
  const save = within(dialog).getByRole('button', { name: /save pension period/i });
  const form = accountSelect.closest('form');
  expect(form).not.toBeNull();
  expect(accountSelect).toBeDisabled();
  expect(save).toBeDisabled();
  fireEvent.submit(form!);
  expect(updateCount).toBe(0);

  recovered = true;
  await user.click(within(dialog).getByRole('button', { name: /retry accounts/i }));
  await waitFor(() => expect(accountSelect).not.toBeDisabled());
  expect((accountSelect as HTMLSelectElement).value).toBe('fund1');
  await user.selectOptions(accountSelect, 'fund1');
  expect(save).toBeEnabled();
  await user.click(save);
  await waitFor(() => expect(updateCount).toBe(1));
  expect(updated.account_id).toBe('fund1');
});
