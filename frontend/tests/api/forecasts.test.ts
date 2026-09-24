import { describe, it, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';
import { forecastsApi } from '../../src/api/forecasts';
import type { Forecast, ForecastDetail, ForecastProjection } from '../../src/types/api';

const forecast: Forecast = {
  id: 'fc-1', user_id: 'user-1', name: 'Plan', base_year: 2026, projection_years: 1,
  created_at: '2026-01-01T00:00:00', updated_at: '2026-01-01T00:00:00',
};
const detail: ForecastDetail = { ...forecast, lines: [] };

describe('forecastsApi', () => {
  it('list returns array of forecasts', async () => {
    server.use(
      http.get('/api/v1/forecasts', () => HttpResponse.json([forecast]))
    );
    const result = await forecastsApi.list();
    expect(result).toEqual([forecast]);
  });

  it('get returns a single forecast', async () => {
    server.use(
      http.get('/api/v1/forecasts/fc-1', () => HttpResponse.json(detail))
    );
    const result = await forecastsApi.get('fc-1');
    expect(result).toEqual(detail);
  });

  it('create posts and returns new forecast', async () => {
    const body = { name: 'New Plan', base_year: 2026, projection_years: 5 };
    server.use(
      http.post('/api/v1/forecasts', () => HttpResponse.json({ ...detail, id: 'fc-2', ...body }))
    );
    const result = await forecastsApi.create(body);
    expect(result).toMatchObject({ id: 'fc-2', name: 'New Plan' });
  });

  it('update puts and returns updated forecast', async () => {
    server.use(
      http.put('/api/v1/forecasts/fc-1', () =>
        HttpResponse.json({ ...detail, name: 'Updated Plan', projection_years: 10 })
      )
    );
    const result = await forecastsApi.update('fc-1', { name: 'Updated Plan', projection_years: 10 });
    expect(result).toMatchObject({ id: 'fc-1', name: 'Updated Plan' });
  });

  it('delete calls DELETE endpoint', async () => {
    server.use(
      http.delete('/api/v1/forecasts/fc-1', () => HttpResponse.json({ ok: true }))
    );
    await expect(forecastsApi.delete('fc-1')).resolves.toBeDefined();
  });

  it('projection returns forecast projection', async () => {
    const projection: ForecastProjection = {
      forecast_id: 'fc-1', base_year: 2026, projection_years: 1,
      period: { from: '2027-01', to: '2027-12' }, lines: [],
      monthly_totals: Array.from({ length: 12 }, (_, i) => ({ month: `2027-${String(i + 1).padStart(2, '0')}`, total: 0 })),
      yearly_totals: [{ year: 2027, total: 0 }],
    };
    server.use(
      http.get('/api/v1/forecasts/fc-1/projection', () => HttpResponse.json(projection))
    );
    const result = await forecastsApi.projection('fc-1');
    expect(result).toEqual(projection);
  });

  it('addLine posts and returns new line', async () => {
    const body = {
      detail: 'Insurance',
      base_amount: 3200,
      category_id: 'cat-1',
      payment_method_id: 'pm-1',
      billing_day: 5,
      notes: 'Recurring',
    };
    const line = { id: 'line-1', source_transaction_id: null, ...body, adjustments: [] };
    let receivedBody: unknown;
    server.use(
      http.post('/api/v1/forecasts/fc-1/lines', async ({ request }) => {
        receivedBody = await request.json();
        return HttpResponse.json(line);
      })
    );
    const result = await forecastsApi.addLine('fc-1', body);
    expect(receivedBody).toEqual(body);
    expect(result).toEqual(line);
  });

  it('updateLine puts and returns updated line', async () => {
    const body = {
      detail: 'Updated Insurance',
      base_amount: 3500,
      category_id: 'cat-1',
      payment_method_id: 'pm-1',
      billing_day: 10,
      notes: null,
    };
    const line = {
      id: 'line-1', source_transaction_id: null,
      ...body,
      adjustments: [{ id: 'adj-1', valid_from: '2027-06-01', new_amount: 3600, adjustment_type: 'fixed' }],
    };
    let receivedBody: unknown;
    server.use(
      http.put('/api/v1/forecasts/fc-1/lines/line-1', async ({ request }) => {
        receivedBody = await request.json();
        return HttpResponse.json(line);
      })
    );
    const result = await forecastsApi.updateLine('fc-1', 'line-1', body);
    expect(receivedBody).toEqual(body);
    expect(result).toEqual(line);
  });

  it('deleteLine calls DELETE endpoint', async () => {
    server.use(
      http.delete('/api/v1/forecasts/fc-1/lines/line-1', () => HttpResponse.json({ ok: true }))
    );
    await expect(forecastsApi.deleteLine('fc-1', 'line-1')).resolves.toBeDefined();
  });

  it('addAdjustment posts and returns new adjustment', async () => {
    const adj = { id: 'adj-1', forecast_line_id: 'line-1', valid_from: '2027-01-01', new_amount: 5000, adjustment_type: 'fixed' };
    server.use(
      http.post('/api/v1/forecasts/fc-1/lines/line-1/adjustments', () => HttpResponse.json(adj))
    );
    const result = await forecastsApi.addAdjustment('fc-1', 'line-1', { valid_from: '2027-01-01', new_amount: 5000 });
    expect(result).toEqual(adj);
  });

  it('updateAdjustment puts and returns updated adjustment', async () => {
    const adj = { id: 'adj-1', forecast_line_id: 'line-1', valid_from: '2027-06-01', new_amount: 6000, adjustment_type: 'fixed' };
    server.use(
      http.put('/api/v1/forecasts/fc-1/lines/line-1/adjustments/adj-1', () => HttpResponse.json(adj))
    );
    const result = await forecastsApi.updateAdjustment('fc-1', 'line-1', 'adj-1', { new_amount: 6000 });
    expect(result).toEqual(adj);
  });

  it('deleteAdjustment calls DELETE endpoint', async () => {
    server.use(
      http.delete('/api/v1/forecasts/fc-1/lines/line-1/adjustments/adj-1', () =>
        HttpResponse.json({ ok: true })
      )
    );
    await expect(forecastsApi.deleteAdjustment('fc-1', 'line-1', 'adj-1')).resolves.toBeDefined();
  });
});
