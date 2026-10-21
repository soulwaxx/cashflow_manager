import { apiClient } from './client';
import type { PensionOpeningBalanceUpdate, PensionPayrollInputs, PensionSnapshot, PensionSnapshotInput } from '../types/api';

export interface PensionConfig extends PensionPayrollInputs {
  id: string;
  user_id: string;
  account_id: string;
  valid_from: string;
  contribution_periods_by_month: number[];
}

export type PensionConfigInput = Omit<PensionConfig, 'id' | 'user_id'>;

export interface PensionSummary {
  year: number;
  as_of: string;
  config: PensionConfig | null;
  year_to_date: { employee: number; employer: number; tfr: number };
  annualized: {
    employee: number;
    employer: number;
    tfr: number;
    eligible_contributions: number;
    cap_used: number;
    cap_excess: number;
    cap: number;
    cap_scope: string;
    tax_config_valid_from: string;
  };
}

export const pensionApi = {
  listConfigs: () => apiClient.get<PensionConfig[]>('/pension/configs').then((r) => r.data),
  createConfig: (body: PensionConfigInput) => apiClient.post<PensionConfig>('/pension/configs', body).then((r) => r.data),
  updateConfig: (id: string, body: PensionConfigInput) => apiClient.put<PensionConfig>(`/pension/configs/${id}`, body).then((r) => r.data),
  deleteConfig: (id: string) => apiClient.delete(`/pension/configs/${id}`),
  summary: (year: number, asOf: string) => apiClient.get<PensionSummary>('/pension/summary', { params: { year, as_of: asOf } }).then((r) => r.data),
  snapshots: (accountId: string) => apiClient.get<PensionSnapshot[]>(`/pension/accounts/${encodeURIComponent(accountId)}/snapshots`).then((r) => r.data),
  updateOpeningBalance: (accountId: string, body: PensionOpeningBalanceUpdate) =>
    apiClient.patch(`/pension/accounts/${encodeURIComponent(accountId)}/opening-balance`, body),
  saveSnapshot: (accountId: string, asOfMonth: string, body: PensionSnapshotInput) =>
    apiClient.put<PensionSnapshot>(`/pension/accounts/${encodeURIComponent(accountId)}/snapshots/${asOfMonth}`, body).then((r) => r.data),
  deleteSnapshot: (accountId: string, asOfMonth: string) =>
    apiClient.delete(`/pension/accounts/${encodeURIComponent(accountId)}/snapshots/${asOfMonth}`),
};
