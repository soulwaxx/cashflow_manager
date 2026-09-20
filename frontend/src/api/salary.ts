import { apiClient } from './client';
import type { SalaryBreakdown, SalaryConfig } from '../types/api';

interface CalculateParams {
  as_of: string;
  ral: number;
  employer_contrib_rate: number;
  voluntary_contrib_rate: number;
  regional_tax_rate: number;
  municipal_tax_rate: number;
  meal_vouchers_annual?: number;
  welfare_annual?: number;
  salary_months?: number;
}

export const salaryApi = {
  list: () =>
    apiClient.get<SalaryConfig[]>('/salary').then((r) => r.data),
  calculate: (params: CalculateParams) =>
    apiClient.get<SalaryBreakdown>('/salary/calculate', { params }).then((r) => r.data),
  create: (body: Omit<SalaryConfig, 'id' | 'user_id' | 'computed_net_monthly' | 'effective_net_monthly'>) =>
    apiClient.post<SalaryConfig>('/salary', body).then((r) => r.data),
  update: (id: string, body: Partial<SalaryConfig>) =>
    apiClient.put<SalaryConfig>(`/salary/${id}`, body).then((r) => r.data),
  delete: (id: string) =>
    apiClient.delete(`/salary/${id}`),
};
