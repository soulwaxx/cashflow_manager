import type { Asset } from '../../types/api';
import { fmt } from '../../utils/format';

interface Props { assets: Asset[] | undefined; isLoading: boolean; }
function provenance(asset: Asset): string | null {
  if (asset.asset_type !== 'pension') return asset.manual_override !== null ? 'Manual' : null;
  if (!asset.reconciled_as_of_month) return `Estimated through ${asset.projected_through ?? 'selected month'}; no statement reconciliation`;
  if (asset.reconciliation_source === 'legacy_override') return `Legacy override assumed December ${asset.reconciled_as_of_month.slice(0, 4)} (not a statement date); projected through ${asset.projected_through ?? 'selected month'}`;
  const source = asset.reconciliation_source === 'statement' ? 'Statement' : 'Manual reconciliation';
  return `${source} balance €${fmt(asset.reconciled_balance ?? asset.final_amount)} through ${asset.reconciled_as_of_month}; projected through ${asset.projected_through ?? 'selected month'}`;
}

export default function AssetStrip({ assets, isLoading }: Props) {
  if (isLoading) return <div className="bg-surface rounded-lg border border-line p-6 animate-pulse h-20" />;
  return (
    <div className="bg-surface rounded-lg border border-line p-4 flex flex-wrap gap-4">
      {(assets ?? []).map((asset) => (
        <div key={asset.account_id ?? `${asset.asset_type}-${asset.asset_name}`} className="flex flex-col">
          <span className="text-xs text-muted">{asset.asset_name}</span>
          <span className="font-semibold text-primary">€{fmt(asset.final_amount)}</span>
          {provenance(asset) && <span className="text-xs text-muted">{provenance(asset)}</span>}
          {asset.asset_type === 'pension' && <span className="text-xs text-muted">Employee €{fmt(asset.employee_contributions ?? 0)} · Employer €{fmt(asset.employer_contributions ?? 0)} · TFR €{fmt(asset.tfr_contributions ?? 0)} · transfers €{fmt(asset.net_transfers ?? 0)}</span>}
        </div>
      ))}
    </div>
  );
}
