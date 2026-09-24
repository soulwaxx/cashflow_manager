import { http, HttpResponse } from 'msw';

export const handlers = [
  http.get('/api/v1/auth/config', () =>
    HttpResponse.json({
      oidc_enabled: true,
      basic_auth_enabled: true,
    })
  ),
  http.get('/api/v1/auth/me', () =>
    HttpResponse.json({
      id: 'user-1',
      email: 'test@example.com',
      name: 'Test User',
      has_password: true,
      has_oidc: false,
    })
  ),
  http.get('/api/v1/onboarding/status', () =>
    HttpResponse.json({ complete: true })
  ),
  http.get('/api/v1/summary/:year/:month', ({ params }) => {
    const year = Number(params.year);
    const month = Number(params.month);
    return HttpResponse.json({
      year, month,
      incomes: 0,
      outcomes_by_method: {},
      transfers_out_bank: 0,
      transfers_in_bank: 0,
      bank_balance: 0,
    });
  }),
  http.get('/api/v1/assets/:year', () =>
    HttpResponse.json([])
  ),
  http.get('/api/v1/tax-config', () =>
    HttpResponse.json([])
  ),
  http.get('/api/v1/payment-methods', () =>
    HttpResponse.json([])
  ),
  http.get('/api/v1/accounts', () =>
    HttpResponse.json([])
  ),
  http.get('/api/v1/categories', () =>
    HttpResponse.json([])
  ),
  http.get('/api/v1/forecasts', () =>
    HttpResponse.json([])
  ),
];
