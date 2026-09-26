import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { assetsApi } from '../api/assets';
import { Button } from '../components/ui/Button';
import Modal from '../components/ui/Modal';
import { Input } from '../components/ui/Input';
import { Select } from '../components/ui/Select';
import { accountsApi } from '../api/accounts';
import { queryKeys, invalidateAssetOverride, invalidateFor } from '../api/queryKeys';
import type { Asset } from '../types/api';
import { fmt } from '../utils/format';

function assetKey(asset: Asset): string {
  return asset.account_id ?? `${asset.asset_type}-${asset.asset_name}`;
}

interface AssetEntryProps {
  asset: Asset;
  editing: boolean;
  override: string;
  isPending: boolean;
  onStartEditing: () => void;
  onOverrideChange: (value: string) => void;
  onSave: () => void;
  onCancel: () => void;
  layout: 'row' | 'card';
}

function AssetEntry({ asset, editing, override, isPending, onStartEditing, onOverrideChange, onSave, onCancel, layout }: AssetEntryProps) {
  const editor = (
    <div className="flex flex-wrap items-center gap-2">
      <input
        aria-label={`Override amount for ${asset.asset_name}`}
        type="number"
        step="0.01"
        value={override}
        onChange={(event) => onOverrideChange(event.target.value)}
        className="border border-line-strong rounded px-3 py-2 min-h-11 w-32 text-sm bg-elevated text-primary"
      />
      <Button className="min-h-11" isLoading={isPending} onClick={onSave}>Save</Button>
      <Button variant="ghost" className="min-h-11" onClick={onCancel}>Cancel</Button>
    </div>
  );

  if (layout === 'row') {
    return (
      <tr className="border-b border-line text-primary">
        <td className="p-3">{asset.asset_name}</td>
        <td className="p-3 capitalize text-muted">{asset.asset_type}</td>
        <td className="p-3 text-right tabular-nums">€{fmt(asset.computed_amount)}</td>
        <td className="p-3 text-right tabular-nums">
          {asset.manual_override !== null ? (
            <span className="text-yellow-700 dark:text-yellow-300 font-medium">€{fmt(asset.manual_override)} <span className="text-xs">(manual)</span></span>
          ) : '—'}
        </td>
        <td className="p-3 text-right tabular-nums font-semibold">€{fmt(asset.final_amount)}</td>
        <td className="p-3">
          {editing ? editor : <Button variant="ghost" className="text-xs min-h-11" aria-label={`Override ${asset.asset_name}`} onClick={onStartEditing}>Override</Button>}
        </td>
      </tr>
    );
  }

  return (
      <article className="sm:hidden rounded-xl border border-line bg-surface p-4 text-primary">
        <div className="flex items-start justify-between gap-3">
          <div><h2 className="font-semibold">{asset.asset_name}</h2><p className="text-xs capitalize text-muted">{asset.asset_type}</p></div>
          <span className="text-right font-semibold tabular-nums">€{fmt(asset.final_amount)}<span className="block text-xs font-normal text-muted">Final value</span></span>
        </div>
        <details className="mt-3 text-sm text-secondary">
          <summary className="min-h-11 min-w-[8rem] cursor-pointer flex items-center">Value details</summary>
          <dl className="grid grid-cols-2 gap-2 py-2">
            <dt>Computed</dt><dd className="text-right tabular-nums">€{fmt(asset.computed_amount)}</dd>
            <dt>Manual override</dt><dd className="text-right tabular-nums">{asset.manual_override !== null ? `€${fmt(asset.manual_override)}` : '—'}</dd>
          </dl>
        </details>
        {editing ? editor : <Button variant="secondary" className="w-full mt-2 min-h-11" aria-label={`Override ${asset.asset_name}`} onClick={onStartEditing}>Override</Button>}
      </article>
  );
}

export default function AssetsPage() {
  const [year, setYear] = useState(() => new Date().getFullYear());
  const [inputYear, setInputYear] = useState(() => String(new Date().getFullYear()));
  const [addOpen, setAddOpen] = useState(false);
  const [newName, setNewName] = useState('');
  const [newType, setNewType] = useState<'saving' | 'investment'>('saving');
  const [newBalance, setNewBalance] = useState('');
  const [editingAssetKey, setEditingAssetKey] = useState<string | null>(null);
  const [overrideValue, setOverrideValue] = useState('');

  const qc = useQueryClient();
  const asOf = `${year}-12-01`;

  const { data: assets = [], isLoading } = useQuery({
    queryKey: queryKeys.assets.asOf(year, asOf),
    queryFn: () => assetsApi.year(year, asOf),
  });

  const { mutate: saveOverride, isPending: savingOverride } = useMutation({
    mutationFn: ({ asset, amount }: { asset: Asset; amount: number | null }) =>
      assetsApi.setOverride(year, asset.asset_type, asset.account_id ?? asset.asset_name, amount),
    onSuccess: () => {
      invalidateAssetOverride(qc, year);
      setEditingAssetKey(null);
    },
  });

  const { mutate: addAccount, isPending: adding } = useMutation({
    mutationFn: () =>
      accountsApi.create({
        type: newType,
        name: newName.trim(),
        opening_balance: parseFloat(newBalance) || 0,
      }),
    onSuccess: () => {
      invalidateFor(qc, 'account');
      setAddOpen(false);
      setNewName('');
      setNewBalance('');
    },
  });

  function startEditing(asset: Asset) {
    setEditingAssetKey(assetKey(asset));
    setOverrideValue(String(asset.manual_override ?? ''));
  }

  function commitOverride(asset: Asset) {
    saveOverride({ asset, amount: overrideValue ? parseFloat(overrideValue) : null });
  }

  return (
    <div className="max-w-4xl space-y-4">
      <div className="flex items-center gap-4">
        <h1 className="text-xl font-bold text-primary">Assets</h1>
        <input
          type="number"
          aria-label="Assets year"
          value={inputYear}
          onChange={(e) => {
            setInputYear(e.target.value);
            const parsed = parseInt(e.target.value, 10);
            if (!isNaN(parsed) && parsed >= 2000 && parsed <= 2100) {
              setYear(parsed);
            }
          }}
          className="border border-line-strong rounded px-2 py-1 min-h-11 w-24 text-sm bg-elevated text-primary"
          min="2000"
          max="2100"
        />
        <Button variant="secondary" className="min-h-11" onClick={() => setAddOpen(true)}>+ Add account</Button>
      </div>
      {isLoading ? (
        <div className="animate-pulse h-48 bg-muted-bg rounded" />
      ) : (
        <>
          <div className="hidden sm:block bg-surface rounded-lg border border-line overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-subtle text-left text-primary">
                  <th className="p-3 font-medium">Name</th>
                  <th className="p-3 font-medium">Type</th>
                  <th className="p-3 font-medium text-right">Computed</th>
                  <th className="p-3 font-medium text-right">Override</th>
                  <th className="p-3 font-medium text-right">Final</th>
                  <th className="p-3" />
                </tr>
              </thead>
              <tbody>
                {assets.map((asset) => (
                  <AssetEntry
                    key={assetKey(asset)}
                    asset={asset}
                    layout="row"
                    editing={editingAssetKey === assetKey(asset)}
                    override={overrideValue}
                    isPending={savingOverride}
                    onStartEditing={() => startEditing(asset)}
                    onOverrideChange={setOverrideValue}
                    onSave={() => commitOverride(asset)}
                    onCancel={() => setEditingAssetKey(null)}
                  />
                ))}
              </tbody>
            </table>
          </div>
          <div className="space-y-3 sm:hidden">
            {assets.map((asset) => (
              <AssetEntry
                key={assetKey(asset)}
                asset={asset}
                layout="card"
                editing={editingAssetKey === assetKey(asset)}
                override={overrideValue}
                isPending={savingOverride}
                onStartEditing={() => startEditing(asset)}
                onOverrideChange={setOverrideValue}
                onSave={() => commitOverride(asset)}
                onCancel={() => setEditingAssetKey(null)}
              />
            ))}
          </div>
        </>
      )}
      <Modal open={addOpen} onClose={() => setAddOpen(false)} title="Add account">
        <div className="flex flex-col gap-3">
          <Input
            label="Account name"
            type="text"
            required
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
          />
          <Select
            label="Type"
            options={[
              { value: 'saving', label: 'Saving account' },
              { value: 'investment', label: 'Investment account' },
            ]}
            value={newType}
            onChange={(e) => setNewType(e.target.value as 'saving' | 'investment')}
          />
          <Input
            label="Opening balance (€)"
            type="number"
            step="0.01"
            value={newBalance}
            onChange={(e) => setNewBalance(e.target.value)}
          />
          <Button isLoading={adding} disabled={!newName.trim()} onClick={() => addAccount()}>
            Add
          </Button>
        </div>
      </Modal>
    </div>
  );
}
