import { apiClient } from './client';
import type { Asset } from '../types/api';

export const assetsApi = {
  year: (year: number, asOf: string) =>
    apiClient.get<Asset[]>(`/assets/${year}`, { params: { as_of: asOf } }).then((r) => r.data),
  setOverride: (year: number, assetType: string, accountId: string, amount: number | null) =>
    apiClient.put(`/assets/${year}/${assetType}/${encodeURIComponent(accountId)}`, { manual_override: amount }),
};
