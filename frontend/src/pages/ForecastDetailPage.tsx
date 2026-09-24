import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { forecastsApi } from '../api/forecasts';
import { queryKeys, invalidateForecast } from '../api/queryKeys';
import type { ForecastLine, ForecastLineAdjustment } from '../types/api';
import ForecastGrid from '../components/forecasting/ForecastGrid';
import AdjustmentModal from '../components/forecasting/AdjustmentModal';
import LineModal from '../components/forecasting/LineModal';
import { forecastError } from '../components/forecasting/forecastErrors';
import { Button } from '../components/ui/Button';
import { fmt } from '../utils/format';

export default function ForecastDetailPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const [lineEditor, setLineEditor] = useState<ForecastLine | 'new' | null>(null);
  const [adjustmentEditor, setAdjustmentEditor] = useState<{
    lineId: string; adjustment?: ForecastLineAdjustment;
  } | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const { data: forecast, isError: forecastErrorState } = useQuery({
    queryKey: queryKeys.forecasts.detail(id!),
    queryFn: () => forecastsApi.get(id!),
    enabled: !!id,
  });

  const { data: projection, isLoading, isError: projectionError } = useQuery({
    queryKey: queryKeys.forecasts.projection(id!),
    queryFn: () => forecastsApi.projection(id!),
    enabled: !!id,
  });

  const refresh = () => {
    invalidateForecast(qc, id!);
    setActionError(null);
  };
  const { mutate: deleteLine, isPending: deletingLine } = useMutation({
    mutationFn: (lineId: string) => forecastsApi.deleteLine(id!, lineId),
    onSuccess: refresh,
    onError: (error: unknown) => setActionError(forecastError(error).message),
  });
  const { mutate: deleteAdjustment, isPending: deletingAdjustment } = useMutation({
    mutationFn: ({ lineId, adjId }: { lineId: string; adjId: string }) =>
      forecastsApi.deleteAdjustment(id!, lineId, adjId),
    onSuccess: refresh,
    onError: (error: unknown) => setActionError(forecastError(error).message),
  });

  if (!id) return null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-primary">{forecast?.name ?? 'Forecast'}</h1>
          {forecast && (
            <p className="text-sm text-muted">
              Base year: {forecast.base_year} · {forecast.projection_years}-year projection
            </p>
          )}
        </div>
        <Button onClick={() => setLineEditor('new')}>+ Add commitment</Button>
      </div>
      {(forecastErrorState || projectionError) && <p role="alert" className="text-sm text-red-600">Could not load forecast. Please try again.</p>}
      {actionError && <p role="alert" className="text-sm text-red-600">{actionError}</p>}

      {forecast && (
        <section aria-label="Commitments" className="space-y-3">
          {forecast.lines.length === 0 && <p className="text-sm text-muted">No commitments yet. Add one to start projecting.</p>}
          {forecast.lines.map((line) => (
            <div key={line.id} className="bg-surface rounded-lg border border-line p-4 space-y-2">
              <div className="flex flex-wrap justify-between items-center gap-2">
                <div>
                  <span className="font-medium text-primary">{line.detail}</span>
                  <span className="text-sm text-muted ml-2">€{fmt(line.base_amount)}/month</span>
                  {line.source_transaction_id && <span className="text-xs text-faint ml-2">Imported · editable snapshot</span>}
                </div>
                <div className="flex gap-2">
                  <Button variant="secondary" onClick={() => setLineEditor(line)}>Edit commitment</Button>
                  <Button variant="ghost" disabled={deletingLine} onClick={() => {
                    if (window.confirm(`Delete ${line.detail} and its ${line.adjustments.length} adjustment(s)?`)) deleteLine(line.id);
                  }}>Delete commitment</Button>
                </div>
              </div>
              <div className="space-y-1">
                {line.adjustments.map((adj) => (
                  <div key={adj.id} className="flex flex-wrap items-center gap-2 text-sm text-secondary">
                    <span>{adj.valid_from.slice(0, 7)}: {adj.adjustment_type === 'percentage' ? `${adj.new_amount}%` : `€${fmt(adj.new_amount)}`}</span>
                    <Button variant="ghost" onClick={() => setAdjustmentEditor({ lineId: line.id, adjustment: adj })}>Edit adjustment</Button>
                    <Button variant="ghost" disabled={deletingAdjustment} onClick={() => deleteAdjustment({ lineId: line.id, adjId: adj.id })}>Delete adjustment</Button>
                  </div>
                ))}
                <Button variant="secondary" onClick={() => setAdjustmentEditor({ lineId: line.id })}>+ Add adjustment</Button>
              </div>
            </div>
          ))}
        </section>
      )}

      {isLoading ? (
        <div className="animate-pulse h-48 bg-muted-bg rounded" />
      ) : projection ? (
        <div className="bg-surface rounded-lg border border-line p-4">
          <ForecastGrid projection={projection} onAddAdjustment={(lineId) => setAdjustmentEditor({ lineId })} />
        </div>
      ) : null}

      {lineEditor && <LineModal forecastId={id} line={lineEditor === 'new' ? undefined : lineEditor} onClose={() => setLineEditor(null)} />}
      {adjustmentEditor && (
        <AdjustmentModal
          open onClose={() => setAdjustmentEditor(null)} forecastId={id} lineId={adjustmentEditor.lineId}
          adjustment={adjustmentEditor.adjustment}
          startMonth={forecast ? `${forecast.base_year + 1}-01` : undefined}
          endMonth={forecast ? `${forecast.base_year + forecast.projection_years}-12` : undefined}
        />
      )}
    </div>
  );
}
