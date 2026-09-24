import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { forecastsApi } from '../../api/forecasts';
import { queryKeys } from '../../api/queryKeys';
import { Button } from '../ui/Button';

export default function ForecastList() {
  const qc = useQueryClient();
  const navigate = useNavigate();

  const { data: forecasts = [], isLoading } = useQuery({
    queryKey: queryKeys.forecasts.all,
    queryFn: forecastsApi.list,
  });

  const { mutate: deleteForecast } = useMutation({
    mutationFn: (id: string) => forecastsApi.delete(id),
    onSuccess: (_result, id) => {
      qc.invalidateQueries({ queryKey: queryKeys.forecasts.all });
      qc.removeQueries({ queryKey: queryKeys.forecasts.detail(id), exact: true });
      qc.removeQueries({ queryKey: queryKeys.forecasts.projection(id), exact: true });
    },
  });

  if (isLoading) return <div className="animate-pulse h-32 bg-muted-bg rounded" />;

  return (
    <ul className="space-y-2">
      {forecasts.length === 0 && <li className="text-faint text-sm">No forecasts yet</li>}
      {forecasts.map((f) => (
        <li key={f.id} className="bg-surface border border-line rounded-lg p-4 flex items-center justify-between">
          <div>
            <div className="font-medium text-primary">{f.name}</div>
            <div className="text-xs text-muted mt-0.5">
              Base year: {f.base_year} · {f.projection_years} year{f.projection_years > 1 ? 's' : ''} projection
            </div>
          </div>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => navigate(`/forecasting/${f.id}`)}>View</Button>
            <Button variant="ghost" className="text-red-500 text-xs"
              onClick={() => window.confirm('Delete this forecast?') && deleteForecast(f.id)}>
              Delete
            </Button>
          </div>
        </li>
      ))}
    </ul>
  );
}
