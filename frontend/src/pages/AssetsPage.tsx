import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { accountsApi } from '../api/accounts';
import { assetsApi } from '../api/assets';
import { pensionApi } from '../api/pension';
import { queryKeys, invalidateAssetOverride, invalidateFor, invalidatePensionValuation } from '../api/queryKeys';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import Modal from '../components/ui/Modal';
import { Select } from '../components/ui/Select';
import type { Asset, PensionSnapshot, PensionSnapshotInput } from '../types/api';
import { fmt } from '../utils/format';

const ACCOUNT_TYPES = ['saving', 'investment', 'pension'] as const;
const SNAPSHOT_SOURCES = ['statement', 'manual'] as const;
type AccountType = (typeof ACCOUNT_TYPES)[number];
type SnapshotSource = (typeof SNAPSHOT_SOURCES)[number];

interface OpeningDraft { accountId: string; amount: string; month: string; }
interface SnapshotDraft { accountId: string; month: string; amount: string; source: string; notes: string; }
interface SnapshotIdentity { accountId: string; month: string; }

function assetKey(asset: Asset): string {
  return asset.account_id ?? `${asset.asset_type}-${asset.asset_name}`;
}

function errorMessage(error: unknown): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => typeof item === 'object' && item !== null && 'msg' in item ? String(item.msg) : String(item)).join('; ');
  }
  return 'Unable to load or save this information. Please retry.';
}

/** Parse nonnegative Numeric(12, 2) form values using their decimal text, not binary multiplication. */
function nonnegativeMoney(value: string): number | null {
  const text = value.trim();
  if (!/^(?:\d+)(?:\.\d{1,2})?$/.test(text)) return null;
  const parsed = Number(text);
  return Number.isFinite(parsed) && parsed <= 9_999_999_999.99 ? parsed : null;
}

/** The legacy saving/investment override API accepts any finite signed float and null. */
function finiteOverride(value: string): number | null | undefined {
  if (value.trim() === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function isCalendarMonth(value: string): boolean {
  const match = /^(\d{4})-(\d{2})-01$/.exec(value);
  if (!match || Number(match[1]) < 1 || Number(match[1]) > 9999) return false;
  const date = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === value;
}

function isReportingMonth(value: string): boolean {
  return isCalendarMonth(value) && Number(value.slice(0, 4)) >= 2000 && Number(value.slice(0, 4)) <= 2100;
}

function isAccountType(value: string): value is AccountType {
  return (ACCOUNT_TYPES as readonly string[]).includes(value);
}

function isSnapshotSource(value: string): value is SnapshotSource {
  return (SNAPSHOT_SOURCES as readonly string[]).includes(value);
}

function isSnapshotForAccount(value: unknown, accountId: string): value is PensionSnapshot {
  if (typeof value !== 'object' || value === null) return false;
  const snapshot = value as Partial<PensionSnapshot>;
  return typeof snapshot.id === 'string' && typeof snapshot.user_id === 'string' && snapshot.account_id === accountId &&
    typeof snapshot.as_of_month === 'string' && isCalendarMonth(snapshot.as_of_month) &&
    typeof snapshot.balance === 'number' && Number.isFinite(snapshot.balance) && snapshot.balance >= 0 &&
    (isSnapshotSource(String(snapshot.source)) || snapshot.source === 'legacy_override') &&
    (snapshot.notes === null || typeof snapshot.notes === 'string');
}

function pensionProvenance(asset: Asset): string {
  if (!asset.reconciled_as_of_month) return `Estimated through ${asset.projected_through ?? 'selected month'}; no statement reconciliation.`;
  if (asset.reconciliation_source === 'legacy_override') {
    return `Legacy annual override assumed at ${asset.reconciled_as_of_month.slice(0, 4)}-12-01; not a statement date. Projected through ${asset.projected_through ?? 'selected month'}.`;
  }
  const label = asset.reconciliation_source === 'statement' ? 'Statement' : 'Manual reconciliation';
  return `${label} balance €${fmt(asset.reconciled_balance ?? asset.final_amount)} through ${asset.reconciled_as_of_month}; projected through ${asset.projected_through ?? 'selected month'}.`;
}

function pensionComponents(asset: Asset): string {
  return `Employee €${fmt(asset.employee_contributions ?? 0)} · Employer €${fmt(asset.employer_contributions ?? 0)} · TFR €${fmt(asset.tfr_contributions ?? 0)} · Net transfers €${fmt(asset.net_transfers ?? 0)}`;
}

function AssetRows({
  assets,
  editingKey,
  overrideValue,
  overridePending,
  overrideError,
  onStartOverride,
  onOverrideChange,
  onSaveOverride,
  onCancelOverride,
}: {
  assets: Asset[];
  editingKey: string | null;
  overrideValue: string;
  overridePending: boolean;
  overrideError: string | null;
  onStartOverride: (asset: Asset) => void;
  onOverrideChange: (value: string) => void;
  onSaveOverride: (asset: Asset) => void;
  onCancelOverride: () => void;
}) {
  const canSaveOverride = (value: string) => finiteOverride(value) !== undefined;
  const editor = (asset: Asset) => (
    <div className="flex flex-wrap items-center gap-2">
      <input
        aria-label={`Override amount for ${asset.asset_name}`}
        type="number"
        step="any"
        value={overrideValue}
        onChange={(event) => onOverrideChange(event.target.value)}
        className="border border-line-strong rounded px-3 py-2 min-h-11 w-32 text-sm bg-elevated text-primary"
      />
      <Button className="min-h-11" isLoading={overridePending} disabled={!canSaveOverride(overrideValue)} onClick={() => onSaveOverride(asset)}>Save</Button>
      <Button variant="ghost" className="min-h-11" disabled={overridePending} onClick={onCancelOverride}>Cancel</Button>
      {overrideError && <p role="alert">{overrideError}</p>}
    </div>
  );

  return (
    <>
      <div className="hidden sm:block bg-surface rounded-lg border border-line overflow-x-auto">
        <table className="w-full text-sm">
          <thead><tr className="bg-subtle text-left text-primary"><th className="p-3">Name</th><th className="p-3">Type</th><th className="p-3 text-right">Computed</th><th className="p-3 text-right">Override</th><th className="p-3 text-right">Final</th><th className="p-3" /></tr></thead>
          <tbody>{assets.map((asset) => {
            const key = assetKey(asset);
            const isEditing = editingKey === key;
            return (
              <tr key={key} className="border-b border-line text-primary">
                <td className="p-3">{asset.asset_name}{asset.asset_type === 'pension' && <><p className="text-xs text-muted">{pensionProvenance(asset)}</p><p className="text-xs text-muted">{pensionComponents(asset)}</p></>}</td>
                <td className="p-3 capitalize text-muted">{asset.asset_type}</td>
                <td className="p-3 text-right tabular-nums">€{fmt(asset.computed_amount)}</td>
                <td className="p-3 text-right tabular-nums">{asset.asset_type === 'pension' ? '—' : asset.manual_override !== null ? `€${fmt(asset.manual_override)} (manual)` : '—'}</td>
                <td className="p-3 text-right tabular-nums font-semibold">€{fmt(asset.final_amount)}</td>
                <td className="p-3">{asset.asset_type !== 'pension' && (isEditing ? editor(asset) : <Button variant="ghost" className="text-xs min-h-11" aria-label={`Override ${asset.asset_name}`} onClick={() => onStartOverride(asset)}>Override</Button>)}</td>
              </tr>
            );
          })}</tbody>
        </table>
      </div>
      <div className="space-y-3 sm:hidden">
        {assets.map((asset) => {
          const key = assetKey(asset);
          const isEditing = editingKey === key;
          return (
            <article key={key} className="rounded-xl border border-line bg-surface p-4 text-primary">
              <div className="flex items-start justify-between gap-3"><div><h2 className="font-semibold">{asset.asset_name}</h2><p className="text-xs capitalize text-muted">{asset.asset_type}</p></div><span className="text-right font-semibold tabular-nums">€{fmt(asset.final_amount)}<span className="block text-xs font-normal text-muted">Final value</span></span></div>
              <details className="mt-3 text-sm text-secondary"><summary className="min-h-11 min-w-[8rem] cursor-pointer flex items-center">Value details</summary><dl className="grid grid-cols-2 gap-2 py-2"><dt>Computed</dt><dd className="text-right tabular-nums">€{fmt(asset.computed_amount)}</dd><dt>Manual override</dt><dd className="text-right tabular-nums">{asset.asset_type === 'pension' || asset.manual_override === null ? '—' : `€${fmt(asset.manual_override)}`}</dd></dl></details>
              {asset.asset_type === 'pension' ? <div className="text-xs text-muted"><p>{pensionProvenance(asset)}</p><p>{pensionComponents(asset)}</p></div> : isEditing ? editor(asset) : <Button variant="secondary" className="w-full mt-2 min-h-11" aria-label={`Override ${asset.asset_name}`} onClick={() => onStartOverride(asset)}>Override</Button>}
            </article>
          );
        })}
      </div>
    </>
  );
}

export default function AssetsPage() {
  const now = new Date();
  const defaultMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-01`;
  const [asOf, setAsOf] = useState(defaultMonth);
  const [addOpen, setAddOpen] = useState(false);
  const [newName, setNewName] = useState('');
  const [newType, setNewType] = useState('saving');
  const [newBalance, setNewBalance] = useState('');
  const [newOpeningMonth, setNewOpeningMonth] = useState(defaultMonth);
  const [editingAssetKey, setEditingAssetKey] = useState<string | null>(null);
  const [overrideValue, setOverrideValue] = useState('');
  const [selectedAccountId, setSelectedAccountId] = useState('');
  const [openingDraft, setOpeningDraft] = useState<OpeningDraft | null>(null);
  const [snapshotDraft, setSnapshotDraft] = useState<SnapshotDraft | null>(null);
  const [editingSnapshot, setEditingSnapshot] = useState<SnapshotIdentity | null>(null);
  const initializedSelection = useRef(false);
  const selectedAccountRef = useRef(selectedAccountId);
  selectedAccountRef.current = selectedAccountId;

  const qc = useQueryClient();
  const reportYear = Number(asOf.slice(0, 4));
  const assetsQuery = useQuery({ queryKey: queryKeys.assets.asOf(reportYear, asOf), queryFn: () => assetsApi.year(reportYear, asOf) });
  const accountsQuery = useQuery({ queryKey: queryKeys.accounts.all, queryFn: () => accountsApi.list() });
  const accounts = Array.isArray(accountsQuery.data) ? accountsQuery.data : [];
  const pensionAccounts = accounts.filter((account) => typeof account?.id === 'string' && account.type === 'pension');

  useEffect(() => {
    if (!accountsQuery.isSuccess || initializedSelection.current || pensionAccounts.length === 0) return;
    initializedSelection.current = true;
    setSelectedAccountId(pensionAccounts[0].id);
  }, [accountsQuery.isSuccess, accountsQuery.data]);

  const activeAccount = pensionAccounts.find((account) => account.id === selectedAccountId);
  const accountListReady = accountsQuery.isSuccess && !accountsQuery.isFetching && !accountsQuery.isError;
  const accountIsMember = !!activeAccount && accountsQuery.isSuccess && !accountsQuery.isError && activeAccount.id === selectedAccountId;
  const historyQuery = useQuery({
    queryKey: accountIsMember ? queryKeys.pension.snapshots(selectedAccountId) : [...queryKeys.pension.snapshots(''), selectedAccountId || 'unselected'],
    queryFn: () => pensionApi.snapshots(selectedAccountId),
    enabled: accountIsMember,
  });
  const snapshots: PensionSnapshot[] = Array.isArray(historyQuery.data) ? historyQuery.data : [];
  const historyEntriesValid = accountIsMember && Array.isArray(historyQuery.data) && snapshots.every((snapshot) => isSnapshotForAccount(snapshot, selectedAccountId));

  useEffect(() => {
    if (!activeAccount) return;
    if (openingDraft?.accountId !== activeAccount.id) {
      setOpeningDraft({ accountId: activeAccount.id, amount: String(activeAccount.opening_balance), month: activeAccount.opening_balance_month ?? '' });
    }
    if (snapshotDraft?.accountId !== activeAccount.id) {
      setSnapshotDraft({ accountId: activeAccount.id, month: defaultMonth, amount: '', source: 'statement', notes: '' });
      setEditingSnapshot(null);
    }
  }, [activeAccount?.id]);

  const openingDraftReady = !!activeAccount && openingDraft?.accountId === activeAccount.id;
  const snapshotDraftReady = !!activeAccount && snapshotDraft?.accountId === activeAccount.id;
  const historyReady = accountIsMember && historyQuery.isSuccess && !historyQuery.isFetching && !historyQuery.isError && historyEntriesValid;

  const addAccount = useMutation({
    mutationFn: (body: { type: AccountType; name: string; opening_balance: number; opening_balance_month?: string }) => accountsApi.create(body),
    onSuccess: () => {
      invalidateFor(qc, 'account');
      invalidatePensionValuation(qc);
      setAddOpen(false);
      setNewName('');
      setNewBalance('');
    },
  });
  const saveOverride = useMutation({
    mutationFn: (variables: { year: number; asset: Asset; amount: number | null }) =>
      assetsApi.setOverride(variables.year, variables.asset.asset_type, variables.asset.account_id ?? variables.asset.asset_name, variables.amount),
    onSuccess: (_result, variables) => {
      invalidateAssetOverride(qc, variables.year);
      setEditingAssetKey(null);
    },
  });
  const saveOpening = useMutation({
    mutationFn: (variables: { accountId: string; accountName: string; amount: number; month: string }) =>
      pensionApi.updateOpeningBalance(variables.accountId, { amount: variables.amount, month: variables.month }),
    onSuccess: async () => {
      await Promise.all([
        qc.invalidateQueries({ queryKey: queryKeys.pension.all }),
        qc.invalidateQueries({ queryKey: queryKeys.assets.all }),
        qc.invalidateQueries({ queryKey: queryKeys.accounts.all }),
      ]);
    },
  });
  const saveSnapshot = useMutation({
    mutationFn: (variables: { accountId: string; accountName: string; month: string; body: PensionSnapshotInput }) =>
      pensionApi.saveSnapshot(variables.accountId, variables.month, variables.body),
    onSuccess: (_result, variables) => {
      void qc.invalidateQueries({ queryKey: queryKeys.pension.snapshots(variables.accountId) });
      invalidatePensionValuation(qc);
      if (selectedAccountRef.current === variables.accountId) setEditingSnapshot(null);
    },
  });
  const deleteSnapshot = useMutation({
    mutationFn: (variables: { accountId: string; accountName: string; month: string }) => pensionApi.deleteSnapshot(variables.accountId, variables.month),
    onSuccess: (_result, variables) => {
      void qc.invalidateQueries({ queryKey: queryKeys.pension.snapshots(variables.accountId) });
      invalidatePensionValuation(qc);
      if (selectedAccountRef.current === variables.accountId) {
        setEditingSnapshot((current) => current?.accountId === variables.accountId && current.month === variables.month ? null : current);
      }
    },
  });

  function changeSelectedAccount(accountId: string) {
    if (saveOpening.isPending && accountId === saveOpening.variables?.accountId && accountId !== selectedAccountId) return;
    setSelectedAccountId(accountId);
    setOpeningDraft(null);
    setSnapshotDraft(null);
    setEditingSnapshot(null);
  }

  function saveOpeningBalance() {
    const accountId = selectedAccountId;
    const draft = openingDraft;
    if (!historyReady || !accountIsMember || !activeAccount || !draft || draft.accountId !== accountId) return;
    const amount = nonnegativeMoney(draft.amount);
    if (amount === null || !isCalendarMonth(draft.month)) return;
    if (snapshots.some((snapshot) => snapshot.as_of_month < draft.month)) return;
    saveOpening.mutate({ accountId, accountName: activeAccount.name, amount, month: draft.month });
  }

  function saveReconciliation() {
    const accountId = selectedAccountId;
    const draft = snapshotDraft;
    if (!historyReady || !accountIsMember || !activeAccount || !draft || draft.accountId !== accountId) return;
    const month = editingSnapshot?.accountId === accountId ? editingSnapshot.month : draft.month;
    const balance = nonnegativeMoney(draft.amount);
    if (balance === null || !isCalendarMonth(month) || !isSnapshotSource(draft.source) || !activeAccount.opening_balance_month || !isCalendarMonth(activeAccount.opening_balance_month) || month < activeAccount.opening_balance_month) return;
    const targetExists = snapshots.some((snapshot) => snapshot.as_of_month === month);
    if (targetExists && editingSnapshot?.accountId !== accountId) return;
    const body: PensionSnapshotInput = { account_id: accountId, as_of_month: month, balance, source: draft.source, notes: draft.notes || null };
    saveSnapshot.mutate({ accountId, accountName: activeAccount.name, month, body });
  }

  function deleteReconciliation(snapshot: PensionSnapshot) {
    const accountId = selectedAccountId;
    if (!historyReady || !accountIsMember || !activeAccount || snapshot.account_id !== accountId || !snapshots.some((item) => item.id === snapshot.id)) return;
    deleteSnapshot.mutate({ accountId, accountName: activeAccount.name, month: snapshot.as_of_month });
  }

  function createAccount() {
    if (!accountListReady || !isAccountType(newType) || !newName.trim()) return;
    const openingBalance = nonnegativeMoney(newBalance);
    if (openingBalance === null) return;
    if (newType === 'pension') {
      if (!isCalendarMonth(newOpeningMonth)) return;
      addAccount.mutate({ type: newType, name: newName.trim(), opening_balance: openingBalance, opening_balance_month: newOpeningMonth });
      return;
    }
    addAccount.mutate({ type: newType, name: newName.trim(), opening_balance: openingBalance });
  }

  function saveAnnualOverride(asset: Asset) {
    if (asset.asset_type === 'pension' || editingAssetKey !== assetKey(asset)) return;
    const amount = finiteOverride(overrideValue);
    if (amount === undefined) return;
    saveOverride.mutate({ year: reportYear, asset, amount });
  }

  const annualOverrideError = saveOverride.isError ? errorMessage(saveOverride.error) : null;
  const openingError = saveOpening.isError && saveOpening.variables?.accountId === selectedAccountId ? errorMessage(saveOpening.error) : null;
  const snapshotError = saveSnapshot.isError && saveSnapshot.variables?.accountId === selectedAccountId ? errorMessage(saveSnapshot.error) : null;
  const deleteError = deleteSnapshot.isError && deleteSnapshot.variables?.accountId === selectedAccountId ? errorMessage(deleteSnapshot.error) : null;
  const accountError = addAccount.isError ? errorMessage(addAccount.error) : null;
  const openingConflict = !!openingDraft && snapshots.some((snapshot) => snapshot.as_of_month < openingDraft.month);
  const editedForSelectedAccount = editingSnapshot?.accountId === selectedAccountId ? editingSnapshot : null;
  const snapshotTargetMonth = editedForSelectedAccount?.month ?? snapshotDraft?.month ?? '';
  const snapshotTargetConflict = !editedForSelectedAccount && snapshots.some((snapshot) => snapshot.as_of_month === snapshotTargetMonth);
  const snapshotReadyToSave = historyReady && snapshotDraftReady && !!activeAccount && !!snapshotDraft && isSnapshotSource(snapshotDraft.source) && nonnegativeMoney(snapshotDraft.amount) !== null && isCalendarMonth(snapshotTargetMonth) && !!activeAccount.opening_balance_month && isCalendarMonth(activeAccount.opening_balance_month) && snapshotTargetMonth >= activeAccount.opening_balance_month && !snapshotTargetConflict;
  const openingReadyToSave = historyReady && openingDraftReady && !!openingDraft && nonnegativeMoney(openingDraft.amount) !== null && isCalendarMonth(openingDraft.month) && !openingConflict;

  const assets = assetsQuery.data ?? [];

  return (
    <div className="max-w-4xl space-y-4">
      <div className="flex flex-wrap items-end gap-4">
        <h1 className="text-xl font-bold text-primary">Assets</h1>
        <Input label="Assets as of month" type="month" value={asOf.slice(0, 7)} onChange={(event) => { const value = event.target.value ? `${event.target.value}-01` : ''; if (isReportingMonth(value)) setAsOf(value); }} />
        <Button variant="secondary" className="min-h-11" disabled={!accountListReady} onClick={() => setAddOpen(true)}>+ Add account</Button>
      </div>

      {assetsQuery.isLoading ? <div className="animate-pulse h-48 bg-muted-bg rounded" /> : assetsQuery.isError ? <div role="alert">{errorMessage(assetsQuery.error)} <Button onClick={() => void assetsQuery.refetch()}>Retry</Button></div> : <AssetRows assets={assets} editingKey={editingAssetKey} overrideValue={overrideValue} overridePending={saveOverride.isPending} overrideError={annualOverrideError} onStartOverride={(asset) => { setEditingAssetKey(assetKey(asset)); setOverrideValue(String(asset.manual_override ?? '')); }} onOverrideChange={setOverrideValue} onSaveOverride={saveAnnualOverride} onCancelOverride={() => setEditingAssetKey(null)} />}

      {accountsQuery.isLoading && <p>Loading accounts…</p>}
      {accountsQuery.isError && <p role="alert">{errorMessage(accountsQuery.error)} <Button onClick={() => void accountsQuery.refetch()}>Retry accounts</Button></p>}
      {accountsQuery.isSuccess && pensionAccounts.length > 0 && <section className="rounded-lg border border-line bg-surface p-4 space-y-3" aria-labelledby="pension-reconciliation-heading">
        <h2 id="pension-reconciliation-heading" className="font-semibold">Pension reconciliation</h2>
        <Select label="Pension account" value={accountIsMember ? selectedAccountId : ''} onChange={(event) => changeSelectedAccount(event.target.value)} options={[{ value: '', label: '— select a pension account —' }, ...pensionAccounts.map((account) => ({ value: account.id, label: account.name }))]} />
        {!selectedAccountId && <p role="status">Select a pension account to load its dated history.</p>}
        {saveOpening.isPending && saveOpening.variables?.accountId !== selectedAccountId && <p role="status">Return to {saveOpening.variables?.accountName} after its opening-balance update and account refresh finish.</p>}
        {!!selectedAccountId && !accountIsMember && <p role="alert">The selected pension account is no longer available. Select a current account; no draft will be retargeted.</p>}
        {accountIsMember && activeAccount && <>
          <p className="text-sm text-secondary">Opening amount is at the start of its month. A reconciliation includes the whole selected month; later months are projected by the backend.</p>
          {!historyReady && historyQuery.isLoading && <p role="status">Loading pension history before enabling balance changes…</p>}
          {!historyReady && historyQuery.isSuccess && !historyEntriesValid && <p role="alert">Pension history contains an invalid or mismatched account entry. Balance changes are disabled; retry history before continuing. <Button onClick={() => void historyQuery.refetch()}>Retry history</Button></p>}
          {openingDraftReady && <div className="grid gap-2 sm:grid-cols-3">
            <Input label="Opening amount (€)" type="number" min="0" step="0.01" value={openingDraft.amount} onChange={(event) => setOpeningDraft({ ...openingDraft, amount: event.target.value })} />
            <Input label="Opening month" type="month" value={openingDraft.month.slice(0, 7)} onChange={(event) => setOpeningDraft({ ...openingDraft, month: event.target.value ? `${event.target.value}-01` : '' })} />
            <Button isLoading={saveOpening.isPending} disabled={!openingReadyToSave || saveOpening.isPending} onClick={saveOpeningBalance}>Save opening balance</Button>
            {openingConflict && <p role="alert">Opening month cannot be after an existing snapshot. Delete or resolve the earlier snapshot first.</p>}
            {openingError && saveOpening.variables && <p role="alert">Opening balance update failed for {saveOpening.variables.accountName} (account {saveOpening.variables.accountId}, {saveOpening.variables.month}): {openingError}</p>}
          </div>}

          <h3 className="font-medium">Dated statement or manual balance</h3>
          {snapshotDraftReady && <div className="grid gap-2 sm:grid-cols-2">
            {editedForSelectedAccount ? <div><Input label="Reconciliation month (editing existing snapshot)" type="month" value={editedForSelectedAccount.month.slice(0, 7)} disabled /><p className="text-xs text-muted">Snapshot date is its identity and cannot be changed here. To correct the date, cancel this edit, delete this snapshot, then add a new one for the corrected month. The two requests are separate; review history after each.</p><Button variant="ghost" disabled={saveSnapshot.isPending || deleteSnapshot.isPending} onClick={() => setEditingSnapshot(null)}>Cancel edit</Button></div> : <Input label="Reconciliation month" type="month" value={snapshotDraft.month.slice(0, 7)} onChange={(event) => setSnapshotDraft({ ...snapshotDraft, month: event.target.value ? `${event.target.value}-01` : '' })} />}
            <Input label="Balance (€)" type="number" min="0" step="0.01" value={snapshotDraft.amount} onChange={(event) => setSnapshotDraft({ ...snapshotDraft, amount: event.target.value })} />
            <Select label="Source" value={snapshotDraft.source} onChange={(event) => setSnapshotDraft({ ...snapshotDraft, source: event.target.value })} options={[{ value: '', label: '— select a source —' }, ...SNAPSHOT_SOURCES.map((source) => ({ value: source, label: source === 'statement' ? 'Statement' : 'Manual' }))]} />
            <Input label="Notes" value={snapshotDraft.notes} onChange={(event) => setSnapshotDraft({ ...snapshotDraft, notes: event.target.value })} />
            <Button isLoading={saveSnapshot.isPending} disabled={!snapshotReadyToSave || saveSnapshot.isPending || deleteSnapshot.isPending} onClick={saveReconciliation}>{editedForSelectedAccount ? 'Save snapshot changes' : 'Save reconciliation'}</Button>
            {snapshotTargetConflict && <p role="alert">A snapshot already exists for this month. Use Edit on that history entry to change it; this form will not overwrite it.</p>}
            {snapshotError && saveSnapshot.variables && <p role="alert">Reconciliation save failed for {saveSnapshot.variables.accountName} (account {saveSnapshot.variables.accountId}, {saveSnapshot.variables.month}): {snapshotError}</p>}
          </div>}
          <h3 className="font-medium">Reconciliation history</h3>
          {historyQuery.isLoading ? <p>Loading history…</p> : historyQuery.isError ? <p role="alert">{errorMessage(historyQuery.error)} <Button onClick={() => void historyQuery.refetch()}>Retry history</Button></p> : !historyEntriesValid ? null : snapshots.length === 0 ? <p>No dated reconciliations. Opening balance alone is not a statement reconciliation.</p> : <ul className="space-y-2">{snapshots.map((snapshot) => <li key={snapshot.id} className="flex flex-wrap items-center gap-2"><span>{snapshot.as_of_month}: €{fmt(snapshot.balance)} — {snapshot.source === 'legacy_override' ? 'legacy annual override (assumed December, not a statement date)' : snapshot.source}{snapshot.notes ? ` · ${snapshot.notes}` : ''}</span><Button variant="ghost" disabled={!historyReady || saveSnapshot.isPending || deleteSnapshot.isPending} onClick={() => { if (!historyReady || snapshot.account_id !== selectedAccountId || !snapshots.some((item) => item.id === snapshot.id)) return; setEditingSnapshot({ accountId: selectedAccountId, month: snapshot.as_of_month }); setSnapshotDraft({ accountId: selectedAccountId, month: snapshot.as_of_month, amount: String(snapshot.balance), source: snapshot.source === 'statement' ? 'statement' : 'manual', notes: snapshot.notes ?? '' }); }}>Edit</Button><Button variant="ghost" isLoading={deleteSnapshot.isPending} disabled={!historyReady || saveSnapshot.isPending || deleteSnapshot.isPending} onClick={() => deleteReconciliation(snapshot)}>Delete</Button></li>)}</ul>}
          {deleteError && deleteSnapshot.variables && <p role="alert">Reconciliation deletion failed for {deleteSnapshot.variables.accountName} (account {deleteSnapshot.variables.accountId}, {deleteSnapshot.variables.month}): {deleteError}</p>}
        </>}
      </section>}

      {addAccount.isError && <p role="alert">{accountError}</p>}
      <Modal open={addOpen} onClose={() => setAddOpen(false)} title="Add account">
        <div className="flex flex-col gap-3">
          <Input label="Account name" required value={newName} onChange={(event) => setNewName(event.target.value)} />
          <Select label="Type" options={[{ value: '', label: '— select —' }, { value: 'saving', label: 'Saving account' }, { value: 'investment', label: 'Investment account' }, { value: 'pension', label: 'Pension account' }]} value={newType} onChange={(event) => setNewType(event.target.value)} />
          <Input label="Opening balance (€)" type="number" min="0" step="0.01" value={newBalance} onChange={(event) => setNewBalance(event.target.value)} />
          {newType === 'pension' && <Input label="Opening balance month" type="month" value={newOpeningMonth.slice(0, 7)} onChange={(event) => setNewOpeningMonth(event.target.value ? `${event.target.value}-01` : '')} />}
          <Button isLoading={addAccount.isPending} disabled={!accountListReady || !isAccountType(newType) || !newName.trim() || nonnegativeMoney(newBalance) === null || (newType === 'pension' && !isCalendarMonth(newOpeningMonth)) || addAccount.isPending} onClick={createAccount}>Add</Button>
        </div>
      </Modal>
    </div>
  );
}
