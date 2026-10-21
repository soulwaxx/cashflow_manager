import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';
import { AuthProvider } from '../../src/contexts/AuthContext';
import AssetsPage from '../../src/pages/AssetsPage';

interface Statement { month: string; balance: number; notes: string | null; source: 'statement' | 'manual'; }
type SnapshotSource = 'statement' | 'manual';
let statement: Statement | null;
let savingOverride: number | null;
const opening = { month: '2025-01-01', balance: 10_000 };

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}><MemoryRouter><AuthProvider>{children}</AuthProvider></MemoryRouter></QueryClientProvider>;
}

async function selectAssetsMonth(month: string) {
  const input = await screen.findByLabelText('Assets as of month');
  const value = month.slice(0, 7);
  fireEvent.change(input, { target: { value } });
  await waitFor(() => expect(input).toHaveValue(value));
  return input;
}

function monthIndex(value: string): number {
  const [year, month] = value.slice(0, 7).split('-').map(Number);
  return year * 12 + month;
}

function backendPensionAsset(asOf: string, candidateStatement: Statement | null = statement) {
  const selectedSnapshot = candidateStatement && candidateStatement.month <= asOf ? candidateStatement : null;
  const baselineMonth = selectedSnapshot?.month ?? opening.month;
  const baseline = selectedSnapshot?.balance ?? opening.balance;
  const flowMonths = Math.max(0, monthIndex(asOf) - monthIndex(baselineMonth));
  const openingMonths = Math.max(0, monthIndex(asOf) - monthIndex(opening.month) + 1);
  const employee = selectedSnapshot ? flowMonths * 25 : openingMonths * 25;
  const employer = selectedSnapshot ? flowMonths * 50 : openingMonths * 50;
  const tfr = selectedSnapshot ? flowMonths * 200 : openingMonths * 200;
  const status = selectedSnapshot ? (selectedSnapshot.source === 'statement' ? 'statement_reconciled' : 'manual_reconciled') : 'estimated';
  const computed = selectedSnapshot ? baseline + flowMonths * 275 : baseline + openingMonths * 275;
  return {
    asset_type: 'pension', asset_name: 'Renamed fund', account_id: 'fund-a',
    computed_amount: computed, manual_override: null, final_amount: computed,
    valuation_status: status,
    reconciled_as_of_month: selectedSnapshot?.month ?? null,
    reconciled_balance: selectedSnapshot?.balance ?? null,
    reconciliation_source: selectedSnapshot?.source ?? null,
    employee_contributions: employee, employer_contributions: employer, tfr_contributions: tfr,
    net_transfers: 0, projected_through: asOf,
  };
}

function backendAssets(asOf: string) {
  const computedSaving = 8000;
  return [
    { asset_type: 'saving', asset_name: 'EmergencyFund', account_id: 'account-1', computed_amount: computedSaving, manual_override: savingOverride, final_amount: savingOverride ?? computedSaving },
    backendPensionAsset(asOf),
  ];
}

function ownedAccounts(openingBalance = opening.balance, openingMonth = opening.month) {
  return [
    { id: 'fund-a', user_id: 'user-1', type: 'pension', name: 'Renamed fund', opening_balance: openingBalance, opening_balance_month: openingMonth, is_active: true },
    { id: 'fund-b', user_id: 'user-1', type: 'pension', name: 'Second fund', opening_balance: 250, opening_balance_month: '2025-01-01', is_active: true },
  ];
}

function useTwoAccountHistory() {
  server.use(
    http.get('/api/v1/accounts', () => HttpResponse.json(ownedAccounts(100, '2025-01-01'))),
    http.get('/api/v1/pension/accounts/fund-a/snapshots', () => HttpResponse.json([{ id: 'a-march', user_id: 'user-1', account_id: 'fund-a', as_of_month: '2026-03-01', balance: 20000, source: 'statement', notes: null }])),
    http.get('/api/v1/pension/accounts/fund-b/snapshots', () => HttpResponse.json([])),
  );
}

beforeEach(() => {
  statement = { month: '2026-03-01', balance: 20_000, notes: 'March statement', source: 'statement' };
  savingOverride = null;
  server.use(
    http.get('/api/v1/assets/:year', ({ request }) => {
      const asOf = new URL(request.url).searchParams.get('as_of');
      return asOf ? HttpResponse.json(backendAssets(asOf)) : HttpResponse.json({ detail: 'Missing as_of' }, { status: 422 });
    }),
    http.get('/api/v1/accounts', () => HttpResponse.json([])),
  );
});

test('AssetsPage renders heading and backend asset values', async () => {
  render(<AssetsPage />, { wrapper });
  await selectAssetsMonth('2026-10-01');
  expect(await screen.findByText('Assets')).toBeInTheDocument();
  expect(await screen.findAllByText('EmergencyFund')).not.toHaveLength(0);
  expect(screen.getAllByText('Renamed fund').length).toBeGreaterThan(0);
  expect(screen.getAllByText(/21\.925/).length).toBeGreaterThan(0);
});

test('mobile asset cards retain accessible value details and non-pension override action', async () => {
  const user = userEvent.setup();
  render(<AssetsPage />, { wrapper });
  const card = (await screen.findAllByRole('article')).find((element) => element.textContent?.includes('EmergencyFund'))!;
  const summary = within(card).getByText('Value details');
  expect(summary).toHaveClass('min-h-11', 'min-w-[8rem]');
  await user.click(summary);
  await user.click(within(card).getByRole('button', { name: 'Override EmergencyFund' }));
  expect(within(card).getByRole('spinbutton', { name: /override amount for emergencyfund/i })).toBeInTheDocument();
});

test('AssetsPage shows backend reconciliation baseline, later components, and no pension annual override', async () => {
  render(<AssetsPage />, { wrapper });
  await selectAssetsMonth('2026-10-01');
  await screen.findAllByText('Renamed fund');
  expect(screen.getAllByText(/21\.925/).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/statement balance €20\.000,00 through 2026-03-01; projected through 2026-10-01/i).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/Employee €175,00 · Employer €350,00 · TFR €1\.400,00 · Net transfers €0,00/).length).toBeGreaterThan(0);
  expect(screen.queryByRole('button', { name: 'Override Renamed fund' })).not.toBeInTheDocument();
});

test('snapshot month equals backend statement and the later month shows only backend projection', async () => {
  let requested: string | null = null;
  server.use(http.get('/api/v1/assets/:year', ({ request }) => {
    requested = new URL(request.url).searchParams.get('as_of');
    return HttpResponse.json(backendAssets(requested!));
  }));
  render(<AssetsPage />, { wrapper });
  const monthInput = await screen.findByLabelText('Assets as of month');
  fireEvent.change(monthInput, { target: { value: '2026-03' } });
  await waitFor(() => expect(requested).toBe('2026-03-01'));
  expect((await screen.findAllByText(/statement balance €20\.000,00 through 2026-03-01; projected through 2026-03-01/i)).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/20\.000/).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/Employee €0,00 · Employer €0,00 · TFR €0,00/).length).toBeGreaterThan(0);
  fireEvent.change(monthInput, { target: { value: '2026-04' } });
  await waitFor(() => expect(requested).toBe('2026-04-01'));
  expect((await screen.findAllByText(/statement balance €20\.000,00 through 2026-03-01; projected through 2026-04-01/i)).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/20\.275/).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/Employee €25,00 · Employer €50,00 · TFR €200,00/).length).toBeGreaterThan(0);
});

test('December-to-January pension history carries forward and earlier month ignores future statement', async () => {
  render(<AssetsPage />, { wrapper });
  const monthInput = await screen.findByLabelText('Assets as of month');
  fireEvent.change(monthInput, { target: { value: '2025-12' } });
  expect((await screen.findAllByText(/Estimated through 2025-12-01/)).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/13\.300/).length).toBeGreaterThan(0);
  fireEvent.change(monthInput, { target: { value: '2026-01' } });
  expect((await screen.findAllByText(/Estimated through 2026-01-01/)).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/13\.575/).length).toBeGreaterThan(0);
  fireEvent.change(monthInput, { target: { value: '2026-02' } });
  expect((await screen.findAllByText(/Estimated through 2026-02-01/)).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/13\.850/).length).toBeGreaterThan(0);
});

test('AssetsPage keeps the reporting selector within the bounded report range', async () => {
  let requested: string | null = null;
  server.use(http.get('/api/v1/assets/:year', ({ request }) => { requested = new URL(request.url).searchParams.get('as_of'); return HttpResponse.json(backendAssets(requested!)); }));
  render(<AssetsPage />, { wrapper });
  const monthInput = await selectAssetsMonth('2026-10-01');
  fireEvent.change(monthInput, { target: { value: '1999-12' } });
  expect(monthInput).toHaveValue('2026-10');
  fireEvent.change(monthInput, { target: { value: '2024-02' } });
  await waitFor(() => expect(requested).toBe('2024-02-01'));
});

test('non-pension annual override saves signed finite precision and clears with explicit null', async () => {
  let body: unknown;
  server.use(http.put('/api/v1/assets/2026/saving/account-1', async ({ request }) => {
    body = await request.json();
    savingOverride = (body as { manual_override: number | null }).manual_override;
    return HttpResponse.json({ ok: true });
  }));
  const user = userEvent.setup();
  render(<AssetsPage />, { wrapper });
  await selectAssetsMonth('2026-10-01');
  const card = (await screen.findAllByRole('article')).find((element) => element.textContent?.includes('EmergencyFund'))!;
  await user.click(within(card).getByRole('button', { name: 'Override EmergencyFund' }));
  const input = within(card).getByRole('spinbutton', { name: /override amount for emergencyfund/i });
  await user.type(input, '-100.12345');
  await user.click(within(card).getByRole('button', { name: 'Save' }));
  await waitFor(() => expect(body).toEqual({ manual_override: -100.12345 }));
  expect((await screen.findAllByText(/€-100,12/)).length).toBeGreaterThan(0);
  const updatedCard = (await screen.findAllByRole('article')).find((element) => element.textContent?.includes('EmergencyFund'))!;
  await user.click(within(updatedCard).getByRole('button', { name: 'Override EmergencyFund' }));
  const clearInput = within(updatedCard).getByRole('spinbutton', { name: /override amount for emergencyfund/i });
  await user.clear(clearInput);
  await user.click(within(updatedCard).getByRole('button', { name: 'Save' }));
  await waitFor(() => expect(body).toEqual({ manual_override: null }));
  expect(screen.getAllByText(/8\.000/).length).toBeGreaterThan(0);
});

test('pension creation validates decimal cents and allows a canonical pre-2000 opening month', async () => {
  let body: unknown;
  server.use(http.post('/api/v1/accounts', async ({ request }) => {
    body = await request.json();
    return HttpResponse.json({ id: 'created-fund', user_id: 'user-1', ...body as object, is_active: true });
  }));
  const user = userEvent.setup();
  render(<AssetsPage />, { wrapper });
  await user.click(await screen.findByRole('button', { name: /add account/i }));
  await user.type(screen.getByLabelText(/Account name/i), 'New fund');
  await user.selectOptions(screen.getByLabelText('Type'), 'pension');
  const amount = screen.getByLabelText('Opening balance (€)');
  await user.type(amount, '1.234');
  expect(screen.getByRole('button', { name: /^add$/i })).toBeDisabled();
  await user.clear(amount);
  await user.type(amount, '0.29');
  fireEvent.change(screen.getByLabelText('Opening balance month'), { target: { value: '1999-12' } });
  expect(screen.getByRole('button', { name: /^add$/i })).toBeEnabled();
  await user.click(screen.getByRole('button', { name: /^add$/i }));
  await waitFor(() => expect(body).toEqual({ type: 'pension', name: 'New fund', opening_balance: 0.29, opening_balance_month: '1999-12-01' }));
});

test('opening balance draft keeps a cleared field blank and submits the deliberate replacement', async () => {
  let body: unknown;
  server.use(
    http.get('/api/v1/accounts', () => HttpResponse.json(ownedAccounts(100, '2025-01-01').slice(0, 1))),
    http.get('/api/v1/pension/accounts/fund-a/snapshots', () => HttpResponse.json([])),
    http.patch('/api/v1/pension/accounts/fund-a/opening-balance', async ({ request }) => { body = await request.json(); return HttpResponse.json({}); }),
  );
  const user = userEvent.setup();
  render(<AssetsPage />, { wrapper });
  const amount = await screen.findByLabelText('Opening amount (€)');
  await waitFor(() => expect(amount).toHaveValue(100));
  await user.clear(amount);
  expect(amount).toHaveValue(null);
  expect(screen.getByRole('button', { name: 'Save opening balance' })).toBeDisabled();
  await user.type(amount, '19.99');
  fireEvent.change(screen.getByLabelText('Opening month'), { target: { value: '1999-12' } });
  expect(screen.getByRole('button', { name: 'Save opening balance' })).toBeEnabled();
  await user.click(screen.getByRole('button', { name: 'Save opening balance' }));
  await waitFor(() => expect(body).toEqual({ amount: 19.99, month: '1999-12-01' }));
});

test('opening write blocks a stale account round trip until refetch and preserves newer or blank drafts', async () => {
  let persistedA = { ...ownedAccounts()[0], opening_balance: 100, opening_balance_month: '2025-01-01' };
  let accountFetches = 0;
  let beginRequest!: () => void;
  let releaseRequest!: () => void;
  const requestStarted = new Promise<void>((resolve) => { beginRequest = resolve; });
  const responseGate = new Promise<void>((resolve) => { releaseRequest = resolve; });
  server.use(
    http.get('/api/v1/accounts', () => {
      accountFetches += 1;
      return HttpResponse.json([persistedA, ownedAccounts()[1]]);
    }),
    http.get('/api/v1/pension/accounts/fund-a/snapshots', () => HttpResponse.json([])),
    http.get('/api/v1/pension/accounts/fund-b/snapshots', () => HttpResponse.json([])),
    http.patch('/api/v1/pension/accounts/fund-a/opening-balance', async ({ request }) => {
      const body = await request.json() as { amount: number; month: string };
      beginRequest();
      await responseGate;
      persistedA = { ...persistedA, opening_balance: body.amount, opening_balance_month: body.month };
      return HttpResponse.json(persistedA);
    }),
  );
  const user = userEvent.setup();
  render(<AssetsPage />, { wrapper });
  await screen.findByText(/No dated reconciliations/);
  const accountSelect = screen.getByLabelText('Pension account');
  const amount = screen.getByLabelText('Opening amount (€)');
  const openingMonth = screen.getByLabelText('Opening month');
  await waitFor(() => expect(amount).toHaveValue(100));
  await user.clear(amount);
  await user.type(amount, '200');
  fireEvent.change(openingMonth, { target: { value: '2025-02' } });
  await user.click(screen.getByRole('button', { name: 'Save opening balance' }));
  await requestStarted;

  await user.selectOptions(accountSelect, 'fund-b');
  await waitFor(() => expect(screen.getByLabelText('Opening amount (€)')).toHaveValue(250));
  fireEvent.change(accountSelect, { target: { value: 'fund-a' } });
  expect(accountSelect).toHaveValue('fund-b');
  expect(screen.getByText(/Return to Renamed fund after its opening-balance update and account refresh finish/)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Save opening balance' })).toBeDisabled();

  releaseRequest();
  await waitFor(() => expect(accountFetches).toBeGreaterThan(1));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Save opening balance' })).toBeEnabled());
  expect(persistedA).toMatchObject({ opening_balance: 200, opening_balance_month: '2025-02-01' });
  await user.selectOptions(accountSelect, 'fund-a');
  await waitFor(() => expect(screen.getByLabelText('Opening amount (€)')).toHaveValue(200));
  expect(screen.getByLabelText('Opening month')).toHaveValue('2025-02');

  await user.clear(screen.getByLabelText('Opening amount (€)'));
  expect(screen.getByLabelText('Opening amount (€)')).toHaveValue(null);
  expect(screen.getByRole('button', { name: 'Save opening balance' })).toBeDisabled();
  await user.type(screen.getByLabelText('Opening amount (€)'), '300');
  fireEvent.change(screen.getByLabelText('Opening month'), { target: { value: '2025-03' } });
  expect(screen.getByLabelText('Opening amount (€)')).toHaveValue(300);
  expect(screen.getByLabelText('Opening month')).toHaveValue('2025-03');
});

test('opening PATCH failures stay attributed to their origin through pending and post-failure account switches', async () => {
  let release!: () => void;
  let requestStarted!: () => void;
  let settled = false;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  const started = new Promise<void>((resolve) => { requestStarted = resolve; });
  useTwoAccountHistory();
  server.use(http.patch('/api/v1/pension/accounts/fund-a/opening-balance', async () => {
    requestStarted();
    await gate;
    settled = true;
    return HttpResponse.json({ detail: 'A opening update rejected' }, { status: 503 });
  }));
  const user = userEvent.setup();
  render(<AssetsPage />, { wrapper });
  await screen.findByText(/2026-03-01: €20\.000,00/);
  await user.clear(screen.getByLabelText('Opening amount (€)'));
  await user.type(screen.getByLabelText('Opening amount (€)'), '110');
  await user.click(screen.getByRole('button', { name: 'Save opening balance' }));
  await started;
  await user.selectOptions(screen.getByLabelText('Pension account'), 'fund-b');
  const bAmount = await screen.findByLabelText('Opening amount (€)');
  await waitFor(() => expect(bAmount).toHaveValue(250));
  await user.clear(bAmount);
  await user.type(bAmount, '251');
  expect(screen.getByRole('button', { name: 'Save opening balance' })).toBeDisabled();
  release();
  await waitFor(() => expect(settled).toBe(true));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Save opening balance' })).toBeEnabled());
  expect(screen.queryByText(/A opening update rejected/)).not.toBeInTheDocument();
  expect(bAmount).toHaveValue(251);
  expect(screen.queryByText(/2026-03-01: €20\.000,00/)).not.toBeInTheDocument();

  await user.selectOptions(screen.getByLabelText('Pension account'), 'fund-a');
  expect(await screen.findByText(/Opening balance update failed for Renamed fund \(account fund-a, 2025-01-01\): A opening update rejected/)).toBeInTheDocument();
  expect(screen.getByLabelText('Opening amount (€)')).toHaveValue(100);
  await user.selectOptions(screen.getByLabelText('Pension account'), 'fund-b');
  await waitFor(() => expect(screen.getByRole('button', { name: 'Save opening balance' })).toBeEnabled());
  expect(screen.queryByText(/A opening update rejected/)).not.toBeInTheDocument();
  expect(screen.getByLabelText('Opening amount (€)')).toHaveValue(250);
});

test('snapshot PUT failure stays with the originating account after switching before its response', async () => {
  let release!: () => void;
  let requestStarted!: () => void;
  let settled = false;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  const started = new Promise<void>((resolve) => { requestStarted = resolve; });
  useTwoAccountHistory();
  server.use(http.put('/api/v1/pension/accounts/fund-a/snapshots/:month', async () => {
    requestStarted();
    await gate;
    settled = true;
    return HttpResponse.json({ detail: 'A snapshot update rejected' }, { status: 503 });
  }));
  const user = userEvent.setup();
  render(<AssetsPage />, { wrapper });
  await screen.findByText(/2026-03-01: €20\.000,00/);
  await user.click(screen.getByRole('button', { name: 'Edit' }));
  await user.clear(screen.getByLabelText('Balance (€)'));
  await user.type(screen.getByLabelText('Balance (€)'), '20100');
  await user.click(screen.getByRole('button', { name: 'Save snapshot changes' }));
  await started;
  await user.selectOptions(screen.getByLabelText('Pension account'), 'fund-b');
  await screen.findByText(/No dated reconciliations/);
  const bBalance = screen.getByLabelText('Balance (€)');
  await user.type(bBalance, '99.99');
  expect(screen.getByRole('button', { name: 'Save reconciliation' })).toBeDisabled();
  release();
  await waitFor(() => expect(settled).toBe(true));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Save reconciliation' })).toBeEnabled());
  expect(screen.queryByText(/A snapshot update rejected/)).not.toBeInTheDocument();
  expect(bBalance).toHaveValue(99.99);
  expect(screen.getByText(/No dated reconciliations/)).toBeInTheDocument();
  await user.selectOptions(screen.getByLabelText('Pension account'), 'fund-a');
  expect(await screen.findByText(/Reconciliation save failed for Renamed fund \(account fund-a, 2026-03-01\): A snapshot update rejected/)).toBeInTheDocument();
  expect(screen.getByText(/2026-03-01: €20\.000,00/)).toBeInTheDocument();
  await user.selectOptions(screen.getByLabelText('Pension account'), 'fund-b');
  expect(await screen.findByText(/No dated reconciliations/)).toBeInTheDocument();
  expect(screen.queryByText(/A snapshot update rejected/)).not.toBeInTheDocument();
  expect(screen.getByLabelText('Balance (€)')).toHaveValue(null);
});

test('snapshot DELETE failure stays with its originating account after switching before its response', async () => {
  let release!: () => void;
  let requestStarted!: () => void;
  let settled = false;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  const started = new Promise<void>((resolve) => { requestStarted = resolve; });
  useTwoAccountHistory();
  server.use(http.delete('/api/v1/pension/accounts/fund-a/snapshots/:month', async () => {
    requestStarted();
    await gate;
    settled = true;
    return HttpResponse.json({ detail: 'A snapshot deletion rejected' }, { status: 503 });
  }));
  const user = userEvent.setup();
  render(<AssetsPage />, { wrapper });
  await screen.findByText(/2026-03-01: €20\.000,00/);
  await user.click(screen.getByRole('button', { name: 'Delete' }));
  await started;
  await user.selectOptions(screen.getByLabelText('Pension account'), 'fund-b');
  await screen.findByText(/No dated reconciliations/);
  const bBalance = screen.getByLabelText('Balance (€)');
  await user.type(bBalance, '99.99');
  expect(screen.getByRole('button', { name: 'Save reconciliation' })).toBeDisabled();
  release();
  await waitFor(() => expect(settled).toBe(true));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Save reconciliation' })).toBeEnabled());
  expect(screen.queryByText(/A snapshot deletion rejected/)).not.toBeInTheDocument();
  expect(bBalance).toHaveValue(99.99);
  expect(screen.getByText(/No dated reconciliations/)).toBeInTheDocument();
  await user.selectOptions(screen.getByLabelText('Pension account'), 'fund-a');
  expect(await screen.findByText(/Reconciliation deletion failed for Renamed fund \(account fund-a, 2026-03-01\): A snapshot deletion rejected/)).toBeInTheDocument();
  expect(screen.getByText(/2026-03-01: €20\.000,00/)).toBeInTheDocument();
  await user.selectOptions(screen.getByLabelText('Pension account'), 'fund-b');
  expect(await screen.findByText(/No dated reconciliations/)).toBeInTheDocument();
  expect(screen.queryByText(/A snapshot deletion rejected/)).not.toBeInTheDocument();
  expect(screen.getByLabelText('Balance (€)')).toHaveValue(null);
});

test('account-bound drafts cannot retarget after switching, list reorder, or blank selection', async () => {
  let order = ['fund-a', 'fund-b'];
  const requests: Array<{ account: string; body: unknown }> = [];
  let openingAccount: string | null = null;
  server.use(
    http.get('/api/v1/accounts', () => HttpResponse.json(order.map((id) => ({ ...ownedAccounts()[id === 'fund-a' ? 0 : 1], id })))),
    http.get('/api/v1/pension/accounts/fund-a/snapshots', () => HttpResponse.json([{ id: 'a-march', user_id: 'user-1', account_id: 'fund-a', as_of_month: '2026-03-01', balance: 20000, source: 'statement', notes: 'A' }])),
    http.get('/api/v1/pension/accounts/fund-b/snapshots', () => HttpResponse.json([{ id: 'b-march', user_id: 'user-1', account_id: 'fund-b', as_of_month: '2026-03-01', balance: 300, source: 'statement', notes: 'B' }])),
    http.put('/api/v1/pension/accounts/:account/snapshots/:month', async ({ request, params }) => { requests.push({ account: String(params.account), body: await request.json() }); return HttpResponse.json({}); }),
    http.patch('/api/v1/pension/accounts/:account/opening-balance', async ({ params }) => { openingAccount = String(params.account); return HttpResponse.json({}); }),
  );
  const user = userEvent.setup();
  render(<AssetsPage />, { wrapper });
  expect(await screen.findByText(/2026-03-01: €20\.000,00/)).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Edit' }));
  await user.clear(screen.getByLabelText('Balance (€)'));
  await user.type(screen.getByLabelText('Balance (€)'), '99.99');
  await user.selectOptions(screen.getByLabelText('Pension account'), 'fund-b');
  await waitFor(() => expect(screen.getByLabelText('Balance (€)')).toHaveValue(null));
  expect(screen.getByRole('button', { name: 'Save reconciliation' })).toBeDisabled();
  await user.type(screen.getByLabelText('Opening amount (€)'), '250');
  fireEvent.change(screen.getByLabelText('Opening month'), { target: { value: '2025-01' } });
  order = ['fund-b', 'fund-a'];
  await user.click(screen.getByRole('button', { name: 'Save opening balance' }));
  await waitFor(() => expect(openingAccount).toBe('fund-b'));
  await waitFor(() => expect(screen.getByLabelText('Pension account')).toHaveValue('fund-b'));
  await user.selectOptions(screen.getByLabelText('Pension account'), '');
  expect(screen.queryByRole('button', { name: 'Save opening balance' })).not.toBeInTheDocument();
  expect(requests).toEqual([]);
  await user.selectOptions(screen.getByLabelText('Pension account'), 'fund-b');
  await user.type(screen.getByLabelText('Opening amount (€)'), '250');
  fireEvent.change(screen.getByLabelText('Opening month'), { target: { value: '2025-01' } });
  await waitFor(() => expect(screen.getByRole('button', { name: 'Save opening balance' })).toBeEnabled());
  order = ['fund-a'];
  await user.click(screen.getByRole('button', { name: 'Save opening balance' }));
  await waitFor(() => expect(openingAccount).toBe('fund-b'));
  expect(await screen.findByText(/selected pension account is no longer available/i)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Save opening balance' })).not.toBeInTheDocument();
  expect(requests).toEqual([]);
});

test('opening-balance drafts accept raw decimal cents, preserve zero, and keep the account month', async () => {
  const bodies: unknown[] = [];
  server.use(
    http.get('/api/v1/accounts', () => HttpResponse.json(ownedAccounts().slice(0, 1))),
    http.get('/api/v1/pension/accounts/fund-a/snapshots', () => HttpResponse.json([])),
    http.patch('/api/v1/pension/accounts/fund-a/opening-balance', async ({ request }) => { bodies.push(await request.json()); return HttpResponse.json({}); }),
  );
  const user = userEvent.setup();
  render(<AssetsPage />, { wrapper });
  await screen.findByText(/No dated reconciliations/);
  await user.clear(screen.getByLabelText('Opening amount (€)'));
  expect(screen.getByRole('button', { name: 'Save opening balance' })).toBeDisabled();
  await user.type(screen.getByLabelText('Opening amount (€)'), '19.99');
  await user.click(screen.getByRole('button', { name: 'Save opening balance' }));
  await waitFor(() => expect(bodies[0]).toEqual({ amount: 19.99, month: '2025-01-01' }));
  await user.clear(screen.getByLabelText('Opening amount (€)'));
  await user.type(screen.getByLabelText('Opening amount (€)'), '0');
  await user.click(screen.getByRole('button', { name: 'Save opening balance' }));
  await waitFor(() => expect(bodies[1]).toEqual({ amount: 0, month: '2025-01-01' }));
});

test('successful but mismatched pension history cannot enable any writes', async () => {
  let writes = 0;
  server.use(
    http.get('/api/v1/accounts', () => HttpResponse.json(ownedAccounts().slice(0, 1))),
    http.get('/api/v1/pension/accounts/fund-a/snapshots', () => HttpResponse.json([{ id: 'wrong-owner', user_id: 'user-1', account_id: 'fund-b', as_of_month: '2026-03-01', balance: 200, source: 'statement', notes: null }])),
    http.patch('/api/v1/pension/accounts/fund-a/opening-balance', () => { writes += 1; return HttpResponse.json({}); }),
    http.put('/api/v1/pension/accounts/fund-a/snapshots/:month', () => { writes += 1; return HttpResponse.json({}); }),
  );
  render(<AssetsPage />, { wrapper });
  expect(await screen.findByText(/invalid or mismatched account entry/i)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Save reconciliation' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Save opening balance' })).toBeDisabled();
  expect(writes).toBe(0);
});

test('pending snapshot response remains bound to the original account after selection changes', async () => {
  let release!: () => void;
  const responseGate = new Promise<void>((resolve) => { release = resolve; });
  const submitted: Array<{ account: string; body: unknown }> = [];
  server.use(
    http.get('/api/v1/accounts', () => HttpResponse.json(ownedAccounts())),
    http.get('/api/v1/pension/accounts/fund-a/snapshots', () => HttpResponse.json([{ id: 'a-march', user_id: 'user-1', account_id: 'fund-a', as_of_month: '2026-03-01', balance: 20000, source: 'statement', notes: null }])),
    http.get('/api/v1/pension/accounts/fund-b/snapshots', () => HttpResponse.json([])),
    http.put('/api/v1/pension/accounts/:account/snapshots/:month', async ({ request, params }) => {
      const body = await request.json();
      submitted.push({ account: String(params.account), body });
      await responseGate;
      return HttpResponse.json({ id: 'saved', user_id: 'user-1', account_id: String(params.account), ...(body as object) });
    }),
  );
  const user = userEvent.setup();
  render(<AssetsPage />, { wrapper });
  await screen.findByText(/2026-03-01: €20\.000,00/);
  await user.click(screen.getByRole('button', { name: 'Edit' }));
  await user.clear(screen.getByLabelText('Balance (€)'));
  await user.type(screen.getByLabelText('Balance (€)'), '20100');
  await user.click(screen.getByRole('button', { name: 'Save snapshot changes' }));
  await waitFor(() => expect(submitted[0]).toMatchObject({ account: 'fund-a', body: { account_id: 'fund-a', as_of_month: '2026-03-01', balance: 20100 } }));
  await user.selectOptions(screen.getByLabelText('Pension account'), 'fund-b');
  await waitFor(() => expect(screen.getByLabelText('Balance (€)')).toHaveValue(null));
  release();
  await waitFor(() => expect(screen.getByLabelText('Pension account')).toHaveValue('fund-b'));
  expect(screen.getByLabelText('Balance (€)')).toHaveValue(null);
  expect(submitted[0].account).toBe('fund-a');
});

test('snapshot editor refuses implicit overwrite when the target month already exists', async () => {
  const puts: unknown[] = [];
  server.use(
    http.get('/api/v1/accounts', () => HttpResponse.json(ownedAccounts().slice(0, 1))),
    http.get('/api/v1/pension/accounts/fund-a/snapshots', () => HttpResponse.json([
      { id: 'march', user_id: 'user-1', account_id: 'fund-a', as_of_month: '2026-03-01', balance: 20000, source: 'statement', notes: null },
      { id: 'february', user_id: 'user-1', account_id: 'fund-a', as_of_month: '2026-02-01', balance: 19500, source: 'manual', notes: null },
    ])),
    http.put('/api/v1/pension/accounts/fund-a/snapshots/:month', async ({ request }) => { puts.push(await request.json()); return HttpResponse.json({}); }),
  );
  const user = userEvent.setup();
  render(<AssetsPage />, { wrapper });
  await screen.findByText(/2026-03-01: €20\.000,00/);
  fireEvent.change(screen.getByLabelText('Reconciliation month'), { target: { value: '2026-02' } });
  await user.type(screen.getByLabelText('Balance (€)'), '19000');
  expect(screen.getByRole('button', { name: 'Save reconciliation' })).toBeDisabled();
  expect(screen.getByText(/A snapshot already exists for this month.*Use Edit on that history entry/i)).toBeInTheDocument();
  const februaryEntry = screen.getByText(/2026-02-01: €19\.500,00/).closest('li')!;
  await user.click(within(februaryEntry).getByRole('button', { name: 'Edit' }));
  expect(screen.getByLabelText('Reconciliation month (editing existing snapshot)')).toBeDisabled();
  expect(screen.getByLabelText('Reconciliation month (editing existing snapshot)')).toHaveValue('2026-02');
  expect(puts).toEqual([]);
});

test('blank account type and snapshot source are blocked before any write', async () => {
  let creates = 0;
  let puts = 0;
  server.use(
    http.get('/api/v1/accounts', () => HttpResponse.json(ownedAccounts().slice(0, 1))),
    http.get('/api/v1/pension/accounts/fund-a/snapshots', () => HttpResponse.json([])),
    http.post('/api/v1/accounts', () => { creates += 1; return HttpResponse.json({}); }),
    http.put('/api/v1/pension/accounts/fund-a/snapshots/:month', () => { puts += 1; return HttpResponse.json({}); }),
  );
  const user = userEvent.setup();
  render(<AssetsPage />, { wrapper });
  await screen.findByText(/No dated reconciliations/);
  await user.type(screen.getByLabelText('Balance (€)'), '0.29');
  await user.selectOptions(screen.getByLabelText('Source'), '');
  expect(screen.getByRole('button', { name: 'Save reconciliation' })).toBeDisabled();
  await user.click(screen.getByRole('button', { name: /add account/i }));
  await user.type(screen.getByLabelText(/Account name/i), 'Missing type');
  await user.selectOptions(screen.getByLabelText('Type'), '');
  await user.type(screen.getByLabelText('Opening balance (€)'), '0');
  expect(screen.getByRole('button', { name: /^add$/i })).toBeDisabled();
  expect(puts).toBe(0);
  expect(creates).toBe(0);
});

test('delayed pension history keeps mutations disabled until a fresh response arrives', async () => {
  let release!: () => void;
  const historyGate = new Promise<void>((resolve) => { release = resolve; });
  let writes = 0;
  server.use(
    http.get('/api/v1/accounts', () => HttpResponse.json(ownedAccounts().slice(0, 1))),
    http.get('/api/v1/pension/accounts/fund-a/snapshots', async () => { await historyGate; return HttpResponse.json([]); }),
    http.patch('/api/v1/pension/accounts/fund-a/opening-balance', () => { writes += 1; return HttpResponse.json({}); }),
    http.put('/api/v1/pension/accounts/fund-a/snapshots/:month', () => { writes += 1; return HttpResponse.json({}); }),
  );
  const user = userEvent.setup();
  render(<AssetsPage />, { wrapper });
  expect(await screen.findByText(/Loading pension history before enabling balance changes/)).toBeInTheDocument();
  await user.type(screen.getByLabelText('Balance (€)'), '0.29');
  expect(screen.getByRole('button', { name: 'Save reconciliation' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Save opening balance' })).toBeDisabled();
  expect(writes).toBe(0);
  release();
  expect(await screen.findByText(/No dated reconciliations/)).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Save reconciliation' }));
  await waitFor(() => expect(writes).toBe(1));
});

test('snapshot edit is identity-locked; date correction explicitly deletes and creates, with backend results', async () => {
  let current: Statement | null = { month: '2026-03-01', balance: 20_000, notes: 'Original March', source: 'statement' };
  const bodies: unknown[] = [];
  server.use(
    http.get('/api/v1/accounts', () => HttpResponse.json(ownedAccounts().slice(0, 1))),
    http.get('/api/v1/pension/accounts/fund-a/snapshots', () => HttpResponse.json(current ? [{ id: `snap-${current.month}`, user_id: 'user-1', account_id: 'fund-a', as_of_month: current.month, balance: current.balance, source: current.source, notes: current.notes }] : [])),
    http.put('/api/v1/pension/accounts/fund-a/snapshots/:month', async ({ request, params }) => {
      const body = await request.json() as { balance: number; notes: string | null; source: SnapshotSource; as_of_month: string };
      bodies.push(body);
      current = { month: String(params.month), balance: body.balance, notes: body.notes, source: body.source };
      return HttpResponse.json({ id: `snap-${current.month}`, user_id: 'user-1', account_id: 'fund-a', ...body });
    }),
    http.delete('/api/v1/pension/accounts/fund-a/snapshots/:month', ({ params }) => {
      if (current?.month === params.month) current = null;
      return new HttpResponse(null, { status: 204 });
    }),
    http.get('/api/v1/assets/:year', ({ request }) => {
      const asOf = new URL(request.url).searchParams.get('as_of')!;
      return HttpResponse.json([backendAssets(asOf)[0], backendPensionAsset(asOf, current)]);
    }),
  );
  const user = userEvent.setup();
  render(<AssetsPage />, { wrapper });
  await selectAssetsMonth('2026-10-01');
  await screen.findAllByText(/21\.925/);
  await user.click(await screen.findByRole('button', { name: 'Edit' }));
  expect(screen.getByLabelText('Reconciliation month (editing existing snapshot)')).toBeDisabled();
  expect(screen.getByText(/To correct the date, cancel this edit, delete this snapshot, then add a new one/)).toBeInTheDocument();
  await user.clear(screen.getByLabelText('Balance (€)'));
  await user.type(screen.getByLabelText('Balance (€)'), '20500');
  await user.clear(screen.getByLabelText('Notes'));
  await user.type(screen.getByLabelText('Notes'), 'Corrected statement amount');
  await user.click(screen.getByRole('button', { name: 'Save snapshot changes' }));
  await waitFor(() => expect(bodies[0]).toMatchObject({ account_id: 'fund-a', as_of_month: '2026-03-01', balance: 20500, notes: 'Corrected statement amount' }));
  expect((await screen.findAllByText(/Statement balance €20\.500,00 through 2026-03-01/)).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/22\.425/).length).toBeGreaterThan(0);

  await user.click(await screen.findByRole('button', { name: 'Delete' }));
  expect((await screen.findAllByText(/Estimated through 2026-10-01/)).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/16\.050/).length).toBeGreaterThan(0);
  await waitFor(() => expect(screen.getByText(/No dated reconciliations/)).toBeInTheDocument());

  fireEvent.change(screen.getByLabelText('Reconciliation month'), { target: { value: '2026-02' } });
  await user.clear(screen.getByLabelText('Balance (€)'));
  await user.type(screen.getByLabelText('Balance (€)'), '20000');
  await user.clear(screen.getByLabelText('Notes'));
  await user.type(screen.getByLabelText('Notes'), 'Date-corrected statement');
  await user.click(screen.getByRole('button', { name: 'Save reconciliation' }));
  await waitFor(() => expect(bodies[1]).toMatchObject({ as_of_month: '2026-02-01', balance: 20000, notes: 'Date-corrected statement' }));
  expect(await screen.findByText(/2026-02-01: €20\.000,00/)).toBeInTheDocument();
  expect(screen.queryByText(/2026-03-01: €20\.500,00/)).not.toBeInTheDocument();
  expect((await screen.findAllByText(/Statement balance €20\.000,00 through 2026-02-01; projected through 2026-10-01/)).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/22\.200/).length).toBeGreaterThan(0);
});

test('failed snapshot deletion keeps the existing baseline and does not start date correction creation', async () => {
  let puts = 0;
  server.use(
    http.get('/api/v1/accounts', () => HttpResponse.json(ownedAccounts().slice(0, 1))),
    http.get('/api/v1/pension/accounts/fund-a/snapshots', () => HttpResponse.json([{ id: 'march', user_id: 'user-1', account_id: 'fund-a', as_of_month: '2026-03-01', balance: 20000, source: 'statement', notes: null }])),
    http.delete('/api/v1/pension/accounts/fund-a/snapshots/:month', () => HttpResponse.json({ detail: 'Deletion failed; statement remains' }, { status: 503 })),
    http.put('/api/v1/pension/accounts/fund-a/snapshots/:month', () => { puts += 1; return HttpResponse.json({}); }),
  );
  const user = userEvent.setup();
  render(<AssetsPage />, { wrapper });
  expect(await screen.findByText(/2026-03-01: €20\.000,00/)).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Delete' }));
  expect(await screen.findByText(/Deletion failed; statement remains/)).toBeInTheDocument();
  expect(screen.getByText(/2026-03-01: €20\.000,00/)).toBeInTheDocument();
  expect(puts).toBe(0);
});

test('failed history gates snapshot/opening/delete writes until retry returns valid history', async () => {
  let attempts = 0;
  let writes = 0;
  server.use(
    http.get('/api/v1/accounts', () => HttpResponse.json(ownedAccounts().slice(0, 1))),
    http.get('/api/v1/pension/accounts/fund-a/snapshots', () => {
      attempts += 1;
      return attempts === 1 ? HttpResponse.json({ detail: 'History unavailable' }, { status: 503 }) : HttpResponse.json([]);
    }),
    http.patch('/api/v1/pension/accounts/fund-a/opening-balance', () => { writes += 1; return HttpResponse.json({}); }),
    http.put('/api/v1/pension/accounts/fund-a/snapshots/:month', () => { writes += 1; return HttpResponse.json({}); }),
    http.delete('/api/v1/pension/accounts/fund-a/snapshots/:month', () => { writes += 1; return new HttpResponse(null, { status: 204 }); }),
  );
  const user = userEvent.setup();
  render(<AssetsPage />, { wrapper });
  expect(await screen.findByText('History unavailable')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Save opening balance' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Save reconciliation' })).toBeDisabled();
  expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument();
  expect(writes).toBe(0);
  await user.click(screen.getByRole('button', { name: 'Retry history' }));
  expect(await screen.findByText(/No dated reconciliations/)).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Save opening balance' }));
  await waitFor(() => expect(writes).toBe(1));
});
