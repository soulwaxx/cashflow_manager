import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';
import { salaryApi } from '../../src/api/salary';

describe('salary API contract', () => {
  it('POSTs explicit salary and independently based pension inputs to calculate', async () => {
    let body: unknown;
    server.use(http.post('/api/v1/salary/calculate', async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ computed_net_monthly: 2000 });
    }));
    await salaryApi.calculate({ as_of: '2026-03-01', salary: { ral: 50000, regional_tax_rate: 0, municipal_tax_rate: 0, meal_vouchers_annual: 0, welfare_annual: 0, salary_months: 13 }, pension: { employee_contrib_rate: .01, employee_contrib_annual_base: 30000, employer_contrib_rate: .02, employer_contrib_annual_base: 20000, tfr_contrib_annual: 1000 } });
    expect(body).toEqual({ as_of: '2026-03-01', salary: { ral: 50000, regional_tax_rate: 0, municipal_tax_rate: 0, meal_vouchers_annual: 0, welfare_annual: 0, salary_months: 13 }, pension: { employee_contrib_rate: .01, employee_contrib_annual_base: 30000, employer_contrib_rate: .02, employer_contrib_annual_base: 20000, tfr_contrib_annual: 1000 } });
  });

  it('sends an explicit null pension for no-pension previews', async () => {
    let body: unknown;
    server.use(http.post('/api/v1/salary/calculate', async ({ request }) => { body = await request.json(); return HttpResponse.json({}); }));
    await salaryApi.calculate({ as_of: '2026-01-01', salary: { ral: 30000, regional_tax_rate: 0, municipal_tax_rate: 0, meal_vouchers_annual: 0, welfare_annual: 0, salary_months: 12 }, pension: null });
    expect(body).toHaveProperty('pension', null);
  });

  it('requests selected-month breakdown as a query parameter', async () => {
    let url = '';
    server.use(http.get('/api/v1/salary/breakdown', ({ request }) => { url = new URL(request.url).search; return HttpResponse.json({}); }));
    await salaryApi.breakdown('2025-04-01');
    expect(url).toBe('?as_of=2025-04-01');
  });
});
