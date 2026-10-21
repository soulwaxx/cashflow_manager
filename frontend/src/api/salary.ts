import { apiClient } from './client';
import type { SalaryBreakdown, SalaryConfig, SalaryFields, PensionPayrollInputs } from '../types/api';

export interface SalaryCalculationRequest {
  as_of: string;
  salary: SalaryFields;
  pension: PensionPayrollInputs | null;
}

export type SalaryConfigCreate = SalaryFields & {
  valid_from: string;
  manual_net_override?: number | null;
};

export const salaryApi = {
  list: () => apiClient.get<SalaryConfig[]>('/salary').then((r) => r.data),
  breakdown: (asOf: string) =>
    apiClient.get<SalaryBreakdown>('/salary/breakdown', { params: { as_of: asOf } }).then((r) => r.data),
  calculate: (body: SalaryCalculationRequest) =>
    apiClient.post<SalaryBreakdown>('/salary/calculate', body).then((r) => r.data),
  create: (body: SalaryConfigCreate) =>
    apiClient.post<SalaryConfig>('/salary', body).then((r) => r.data),
  update: (id: string, body: SalaryConfigCreate) =>
    apiClient.put<SalaryConfig>(`/salary/${id}`, body).then((r) => r.data),
  delete: (id: string) => apiClient.delete(`/salary/${id}`),
};
