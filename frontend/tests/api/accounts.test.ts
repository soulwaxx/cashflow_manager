import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { accountsApi } from '../../src/api/accounts';
import type { AccountCreate } from '../../src/types/api';
import { server } from '../mocks/server';

describe('accountsApi', () => {
  it('creates an account with the backend request contract', async () => {
    const request: AccountCreate = {
      type: 'saving',
      name: 'Emergency fund',
      opening_balance: 500,
    };
    server.use(
      http.post('/api/v1/accounts', async ({ request: httpRequest }) => {
        expect(await httpRequest.json()).toEqual(request);
        return HttpResponse.json({
          id: 'account-1', user_id: 'user-1', ...request, is_active: true,
        });
      })
    );

    await expect(accountsApi.create(request)).resolves.toMatchObject(request);
  });

  it('creates a pension account with its required opening month', async () => {
    const request: AccountCreate = { type: 'pension', name: 'Work fund', opening_balance: 0, opening_balance_month: '2026-01-01' };
    server.use(http.post('/api/v1/accounts', async ({ request: httpRequest }) => {
      expect(await httpRequest.json()).toEqual(request);
      return HttpResponse.json({ id: 'pension-1', user_id: 'user-1', ...request, is_active: true });
    }));
    await expect(accountsApi.create(request)).resolves.toMatchObject(request);
  });
});
