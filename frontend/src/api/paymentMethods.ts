import { apiClient } from './client';
import type { PaymentMethod, PaymentMethodUpdate } from '../types/api';

export const paymentMethodsApi = {
  list: (activeOnly = true) =>
    apiClient.get<PaymentMethod[]>('/payment-methods', { params: { active_only: activeOnly } }).then((r) => r.data),
  create: (body: Omit<PaymentMethod, 'id' | 'user_id'>) =>
    apiClient.post<PaymentMethod>('/payment-methods', body).then((r) => r.data),
  update: (id: string, body: PaymentMethodUpdate) =>
    apiClient.put<PaymentMethod>(`/payment-methods/${id}`, body).then((r) => r.data),
  setMainBank: (id: string, openingBalance: number) =>
    apiClient.post(`/payment-methods/${id}/set-main-bank`, { opening_balance: openingBalance }),
  history: () =>
    apiClient.get('/payment-methods/main-bank-history').then((r) => r.data),
};
