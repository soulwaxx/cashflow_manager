import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';
import { pensionApi } from '../../src/api/pension';

describe('pension API contracts', () => {
  it('uses configs collection CRUD routes with independent periods', async () => {
    const requests: Array<{ method: string; path: string; body?: unknown }> = [];
    server.use(
      http.get('/api/v1/pension/configs', ({ request }) => { requests.push({ method: request.method, path: new URL(request.url).pathname }); return HttpResponse.json([]); }),
      http.post('/api/v1/pension/configs', async ({ request }) => { requests.push({ method: request.method, path: new URL(request.url).pathname, body: await request.json() }); return HttpResponse.json({ id: 'p1' }, { status: 201 }); }),
      http.put('/api/v1/pension/configs/p1', async ({ request }) => { requests.push({ method: request.method, path: new URL(request.url).pathname, body: await request.json() }); return HttpResponse.json({ id: 'p1' }); }),
      http.delete('/api/v1/pension/configs/p1', ({ request }) => { requests.push({ method: request.method, path: new URL(request.url).pathname }); return new HttpResponse(null, { status: 204 }); }),
    );
    const input = { account_id: 'owned-fund', valid_from: '2026-07-01', employee_contrib_rate: .01, employee_contrib_annual_base: 30000, employer_contrib_rate: 0, employer_contrib_annual_base: 20000, tfr_contrib_annual: 0, contribution_periods_by_month: [0,0,1,0,0,1,0,0,1,0,0,1] };
    await pensionApi.listConfigs(); await pensionApi.createConfig(input); await pensionApi.updateConfig('p1', input); await pensionApi.deleteConfig('p1');
    expect(requests.map(({ method, path }) => [method, path])).toEqual([['GET','/api/v1/pension/configs'],['POST','/api/v1/pension/configs'],['PUT','/api/v1/pension/configs/p1'],['DELETE','/api/v1/pension/configs/p1']]);
    expect(requests[1].body).toEqual(input);
  });

  it('uses dated snapshot history and the PATCH opening-balance contract', async () => {
    const calls: Array<{ method: string; path: string; body?: unknown }> = [];
    server.use(
      http.get('/api/v1/pension/accounts/fund%2Fone/snapshots', ({ request }) => { calls.push({ method: request.method, path: new URL(request.url).pathname }); return HttpResponse.json([]); }),
      http.patch('/api/v1/pension/accounts/fund%2Fone/opening-balance', async ({ request }) => { calls.push({ method: request.method, path: new URL(request.url).pathname, body: await request.json() }); return HttpResponse.json({}); }),
      http.put('/api/v1/pension/accounts/fund%2Fone/snapshots/2026-03-01', async ({ request }) => { calls.push({ method: request.method, path: new URL(request.url).pathname, body: await request.json() }); return HttpResponse.json({ id: 's1' }); }),
      http.delete('/api/v1/pension/accounts/fund%2Fone/snapshots/2026-03-01', ({ request }) => { calls.push({ method: request.method, path: new URL(request.url).pathname }); return new HttpResponse(null, { status: 204 }); }),
    );
    await pensionApi.snapshots('fund/one');
    await pensionApi.updateOpeningBalance('fund/one', { amount: 0, month: '2026-01-01' });
    await pensionApi.saveSnapshot('fund/one', '2026-03-01', { account_id: 'fund/one', as_of_month: '2026-03-01', balance: 0, source: 'statement', notes: null });
    await pensionApi.deleteSnapshot('fund/one', '2026-03-01');
    expect(calls.map(({ method, path }) => [method, path])).toEqual([
      ['GET', '/api/v1/pension/accounts/fund%2Fone/snapshots'],
      ['PATCH', '/api/v1/pension/accounts/fund%2Fone/opening-balance'],
      ['PUT', '/api/v1/pension/accounts/fund%2Fone/snapshots/2026-03-01'],
      ['DELETE', '/api/v1/pension/accounts/fund%2Fone/snapshots/2026-03-01'],
    ]);
    expect(calls[1].body).toEqual({ amount: 0, month: '2026-01-01' });
  });

  it('requests summary for a matching selected year and month', async () => {
    let search = '';
    server.use(http.get('/api/v1/pension/summary', ({ request }) => { search = new URL(request.url).search; return HttpResponse.json({}); }));
    await pensionApi.summary(2026, '2026-02-01');
    expect(search).toContain('year=2026');
    expect(search).toContain('as_of=2026-02-01');
  });
});
