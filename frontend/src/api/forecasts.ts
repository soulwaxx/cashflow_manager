import { apiClient } from './client';
import type {
  Forecast,
  ForecastDetail,
  ForecastProjection,
  ForecastLine,
  ForecastLineRequest,
  ForecastAdjustment,
} from '../types/api';

export const forecastsApi = {
  list: () =>
    apiClient.get<Forecast[]>('/forecasts').then((r) => r.data),
  get: (id: string) =>
    apiClient.get<ForecastDetail>(`/forecasts/${id}`).then((r) => r.data),
  create: (body: { name: string; base_year: number; projection_years: number }) =>
    apiClient.post<ForecastDetail>('/forecasts', body).then((r) => r.data),
  update: (id: string, body: { name?: string; projection_years?: number }) =>
    apiClient.put<ForecastDetail>(`/forecasts/${id}`, body).then((r) => r.data),
  delete: (id: string) =>
    apiClient.delete(`/forecasts/${id}`),

  projection: (id: string) =>
    apiClient.get<ForecastProjection>(`/forecasts/${id}/projection`).then((r) => r.data),

  addLine: (id: string, body: ForecastLineRequest) =>
    apiClient.post<ForecastLine>(`/forecasts/${id}/lines`, body).then((r) => r.data),
  updateLine: (id: string, lineId: string, body: ForecastLineRequest) =>
    apiClient.put<ForecastLine>(`/forecasts/${id}/lines/${lineId}`, body).then((r) => r.data),
  deleteLine: (id: string, lineId: string) =>
    apiClient.delete(`/forecasts/${id}/lines/${lineId}`),

  addAdjustment: (id: string, lineId: string, body: { valid_from: string; new_amount: number; adjustment_type?: 'fixed' | 'percentage' }) =>
    apiClient.post<ForecastAdjustment>(`/forecasts/${id}/lines/${lineId}/adjustments`, body).then((r) => r.data),
  updateAdjustment: (id: string, lineId: string, adjId: string, body: { valid_from?: string; new_amount?: number; adjustment_type?: 'fixed' | 'percentage' }) =>
    apiClient.put<ForecastAdjustment>(`/forecasts/${id}/lines/${lineId}/adjustments/${adjId}`, body).then((r) => r.data),
  deleteAdjustment: (id: string, lineId: string, adjId: string) =>
    apiClient.delete(`/forecasts/${id}/lines/${lineId}/adjustments/${adjId}`),
};
