import { apiClient } from './client';
import type { Account, AccountCreate } from '../types/api';

export const accountsApi = {
  list: (type?: Account['type']) =>
    apiClient.get<Account[]>('/accounts', { params: type ? { type } : undefined }).then((r) => r.data),
  create: (body: AccountCreate) =>
    apiClient.post<Account>('/accounts', body).then((r) => r.data),
};
