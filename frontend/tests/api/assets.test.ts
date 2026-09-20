import { describe, it, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';
import { assetsApi } from '../../src/api/assets';

describe('assetsApi', () => {
  it('year returns assets for a given as-of month', async () => {
    const assets = [{ id: 'a-1', asset_type: 'stock', asset_name: 'AAPL', amount: 10000 }];
    server.use(
      http.get('/api/v1/assets/2026', ({ request }) => {
        expect(new URL(request.url).searchParams.get('as_of')).toBe('2026-03-01');
        return HttpResponse.json(assets);
      })
    );
    const result = await assetsApi.year(2026, '2026-03-01');
    expect(result).toEqual(assets);
  });

  it('setOverride puts manual override for an asset', async () => {
    server.use(
      http.put('/api/v1/assets/2026/stock/AAPL', () => HttpResponse.json({ ok: true }))
    );
    await expect(assetsApi.setOverride(2026, 'stock', 'AAPL', 12000)).resolves.toBeDefined();
  });

  it('setOverride encodes asset name with spaces', async () => {
    server.use(
      http.put('/api/v1/assets/2026/real_estate/My%20House', () =>
        HttpResponse.json({ ok: true })
      )
    );
    await expect(assetsApi.setOverride(2026, 'real_estate', 'My House', 500000)).resolves.toBeDefined();
  });

  it('setOverride accepts null to clear override', async () => {
    server.use(
      http.put('/api/v1/assets/2026/stock/AAPL', () => HttpResponse.json({ ok: true }))
    );
    await expect(assetsApi.setOverride(2026, 'stock', 'AAPL', null)).resolves.toBeDefined();
  });
});
