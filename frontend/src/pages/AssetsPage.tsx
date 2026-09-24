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

function AssetRow({ asset, year }: { asset: Asset; year: number }) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [override, setOverride] = useState(String(asset.manual_override ?? ''));

  const { mutate, isPending } = useMutation({
    mutationFn: (amount: number | null) =>
      assetsApi.setOverride(year, asset.asset_type, asset.account_id ?? asset.asset_name, amount),
    onSuccess: () => {
      invalidateAssetOverride(qc, year);
      setEditing(false);
    },
  });

  return (
    <tr className="border-b border-line text-primary">
      <td className="p-3">{asset.asset_name}</td>
      <td className="p-3 capitalize text-muted">{asset.asset_type}</td>
      <td className="p-3 text-right tabular-nums">€{fmt(asset.computed_amount)}</td>
      <td className="p-3 text-right tabular-nums">
        {asset.manual_override !== null ? (
          <span className="text-yellow-600 font-medium">€{fmt(asset.manual_override)} <span className="text-xs">(manual)</span></span>
        ) : '—'}
      </td>
      <td className="p-3 text-right tabular-nums font-semibold">€{fmt(asset.final_amount)}</td>
      <td className="p-3">
        {editing ? (
          <div className="flex gap-2 items-center">
            <input
              type="number"
              step="0.01"
              value={override}
              onChange={(e) => setOverride(e.target.value)}
              className="border border-line-strong rounded px-2 py-1 w-28 text-sm bg-elevated text-primary"
            />
            <Button className="text-xs" isLoading={isPending} onClick={() => mutate(override ? parseFloat(override) : null)}>Save</Button>
            <Button variant="ghost" className="text-xs" onClick={() => setEditing(false)}>Cancel</Button>
          </div>
        ) : (
          <Button variant="ghost" className="text-xs" onClick={() => setEditing(true)}>Override</Button>
        )}
      </td>
    </tr>
  );
}

export default function AssetsPage() {
  const [year, setYear] = useState(() => new Date().getFullYear());
  const [inputYear, setInputYear] = useState(() => String(new Date().getFullYear()));
  const [addOpen, setAddOpen] = useState(false);
  const [newName, setNewName] = useState('');
  const [newType, setNewType] = useState<'saving' | 'investment'>('saving');
  const [newBalance, setNewBalance] = useState('');

  const qc = useQueryClient();
  const asOf = `${year}-12-01`;

  const { data: assets = [], isLoading } = useQuery({
    queryKey: queryKeys.assets.asOf(year, asOf),
    queryFn: () => assetsApi.year(year, asOf),
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

  return (
    <div className="max-w-4xl space-y-4">
      <div className="flex items-center gap-4">
        <h1 className="text-xl font-bold text-primary">Assets</h1>
        <input
          type="number"
          value={inputYear}
          onChange={(e) => {
            setInputYear(e.target.value);
            const parsed = parseInt(e.target.value, 10);
            if (!isNaN(parsed) && parsed >= 2000 && parsed <= 2100) {
              setYear(parsed);
            }
          }}
          className="border border-line-strong rounded px-2 py-1 w-24 text-sm bg-elevated text-primary"
          min="2000"
          max="2100"
        />
        <Button variant="secondary" onClick={() => setAddOpen(true)}>+ Add account</Button>
      </div>
      {isLoading ? (
        <div className="animate-pulse h-48 bg-muted-bg rounded" />
      ) : (
        <div className="bg-surface rounded-lg border border-line overflow-x-auto">
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
              {assets.map((a) => (
                <AssetRow key={a.account_id ?? `${a.asset_type}-${a.asset_name}`} asset={a} year={year} />
              ))}
            </tbody>
          </table>
        </div>
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
