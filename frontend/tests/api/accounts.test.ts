import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { accountsApi } from '../../src/api/accounts';
import type { AccountCreate } from '../../src/types/api';
import { server } from '../mocks/server';

describe('accountsApi', () => {
  it('creates a saving or investment account with the backend request contract', async () => {
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

  it('keeps pension out of the create request type', () => {
    // @ts-expect-error Pension accounts are created only from salary contributions.
    const pensionRequest: AccountCreate = { type: 'pension', name: 'Pension' };
    void pensionRequest;
  });
});
