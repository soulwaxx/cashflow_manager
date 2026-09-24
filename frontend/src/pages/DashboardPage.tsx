import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { summaryApi } from '../api/summary';
import { assetsApi } from '../api/assets';
import { queryKeys } from '../api/queryKeys';
import MonthNavigator from '../components/dashboard/MonthNavigator';
import BankBalanceCard from '../components/dashboard/BankBalanceCard';
import OutcomesByMethod from '../components/dashboard/OutcomesByMethod';
import AssetStrip from '../components/dashboard/AssetStrip';

export default function DashboardPage() {
  const [current, setCurrent] = useState(() => new Date());
  const year = current.getFullYear();
  const month = current.getMonth() + 1;
  const asOf = `${year}-${String(month).padStart(2, '0')}-01`;

  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: queryKeys.summary.month(year, month),
    queryFn: () => summaryApi.month(year, month),
  });

  const { data: assets, isLoading: assetsLoading } = useQuery({
    queryKey: queryKeys.assets.asOf(year, asOf),
    queryFn: () => assetsApi.year(year, asOf),
  });

  return (
    <div className="space-y-4 max-w-3xl">
      <div className="flex items-center justify-end">
        <MonthNavigator current={current} onChange={setCurrent} />
      </div>
      <BankBalanceCard summary={summary} isLoading={summaryLoading} />
      <OutcomesByMethod summary={summary} isLoading={summaryLoading} />
      <AssetStrip assets={assets} isLoading={assetsLoading} />
    </div>
  );
}
