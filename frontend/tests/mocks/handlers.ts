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
  http.get('/api/v1/summary/:year', ({ params }) =>
    HttpResponse.json(Array.from({ length: 12 }, (_, index) => ({
      year: Number(params.year),
      month: index + 1,
      incomes: 0,
      outcomes_by_method: {},
      transfers_out_bank: 0,
      transfers_in_bank: 0,
      bank_balance: 0,
    })))
  ),
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
  http.get('/api/v1/salary', () => HttpResponse.json([])),
  http.get('/api/v1/pension/configs', () => HttpResponse.json([])),
  http.get('/api/v1/pension/summary', ({ request }) => {
    const url = new URL(request.url);
    return HttpResponse.json({
      year: Number(url.searchParams.get('year')), as_of: url.searchParams.get('as_of'), config: null,
      year_to_date: { employee: 0, employer: 0, tfr: 0 },
      annualized: { employee: 0, employer: 0, tfr: 0, eligible_contributions: 0, cap_used: 0, cap_excess: 0, cap: 5300, cap_scope: 'Configured ordinary payroll contributions only', tax_config_valid_from: '2026-01-01' },
    });
  }),
  http.get('/api/v1/salary/breakdown', () => HttpResponse.json({ detail: 'No salary configuration applies to this month' }, { status: 404 })),
  http.post('/api/v1/salary/calculate', () => HttpResponse.json({
    gross_annual: 0, social_security: 0, employee_pension_contribution_annual: 0,
    employer_pension_contribution_annual: 0, tfr_contribution_annual: 0,
    pension_payroll_deduction_annual: 0, pension_employer_taxable_excess_annual: 0,
    pension_cap_eligible_contributions_annual: 0, pension_cap_used_annual: 0,
    pension_cap_excess_annual: 0, pension_deductibility_cap: 5300,
    pension_cap_scope: 'Configured ordinary payroll contributions only', tax_config_id: 'tax',
    tax_config_valid_from: '2026-01-01', taxable_base: 0, income_tax_gross: 0,
    employment_deduction: 0, income_tax_net: 0, regional_surtax: 0, municipal_surtax: 0,
    net_annual: 0, computed_net_monthly: 0, meal_vouchers_monthly: 0,
    welfare_monthly: 0, salary_months: 12,
  })),
  http.post('/api/v1/pension/configs', async ({ request }) => HttpResponse.json({ id: 'pension-config', user_id: 'user-1', ...(await request.json() as object) }, { status: 201 })),

  http.get('/api/v1/categories', () =>
    HttpResponse.json([])
  ),
];
