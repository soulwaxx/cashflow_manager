import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';
import { AuthProvider } from '../../src/contexts/AuthContext';
import SalaryPage from '../../src/pages/SalaryPage';

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}><MemoryRouter><AuthProvider>{children}</AuthProvider></MemoryRouter></QueryClientProvider>
  );
}

beforeEach(() => {
  server.use(
    http.get('/api/v1/salary', () =>
      HttpResponse.json([{
        id: 'sc1', user_id: 'u1', valid_from: '2026-01-01', ral: 4000,
        employer_contrib_rate: 0.04, voluntary_contrib_rate: 0, regional_tax_rate: 0.0173,
        municipal_tax_rate: 0.001, meal_vouchers_annual: 0, welfare_annual: 0,
        salary_months: 12, manual_net_override: null, computed_net_monthly: 2600,
      }])
    ),
    http.get('/api/v1/salary/calculate', () =>
      HttpResponse.json({
        gross_annual: 4000, social_security: 367, pension_deductible: 160, taxable_base: 3473,
        income_tax_gross: 841, employment_deduction: 1450, income_tax_net: 0,
        regional_surtax: 60, municipal_surtax: 3,
        net_annual: 3570, net_monthly: 297.5,
        meal_vouchers_monthly: 0, welfare_monthly: 0,
      })
    ),
    http.get('/api/v1/tax-config', () => HttpResponse.json([]))
  );
});

test('SalaryPage renders page content', async () => {
  render(<SalaryPage />, { wrapper });
  await waitFor(() => expect(screen.getByText('Salary Config')).toBeInTheDocument());
});

test('SalaryPage shows salary entry with gross salary value', async () => {
  render(<SalaryPage />, { wrapper });
  // RAL 4000 shown in the period card as "RAL €4.000,00" (Italian locale)
  await waitFor(() => expect(screen.getByText(/4\.000/)).toBeInTheDocument());
});

test('SalaryPage has add period button', async () => {
  render(<SalaryPage />, { wrapper });
  await waitFor(() => expect(screen.getByRole('button', { name: /add period/i })).toBeInTheDocument());
});

test('SalaryPage shows salary config period', async () => {
  render(<SalaryPage />, { wrapper });
  await waitFor(() => expect(screen.getByText('2026-01-01')).toBeInTheDocument());
});

test('Salary breakdown can be expanded and collapsed with the keyboard', async () => {
  const user = userEvent.setup();
  render(<SalaryPage />, { wrapper });
  const toggle = await screen.findByRole('button', { name: /hide breakdown/i });
  expect(toggle).toHaveAttribute('aria-expanded', 'true');
  toggle.focus();
  await user.keyboard('{Enter}');
  expect(toggle).toHaveAttribute('aria-expanded', 'false');
  expect(screen.queryByText('Breakdown')).not.toBeInTheDocument();
  await user.keyboard('{Enter}');
  expect(toggle).toHaveAttribute('aria-expanded', 'true');
});

test('SalaryPage shows computed net monthly', async () => {
  render(<SalaryPage />, { wrapper });
  await waitFor(() => expect(screen.getByText(/2\.600/)).toBeInTheDocument()); // Italian locale: 2.600
});

test('SalaryPage shows salary breakdown when period selected', async () => {
  render(<SalaryPage />, { wrapper });
  await waitFor(() => screen.getByText('2026-01-01'));
  // Breakdown should show INPS
  expect(await screen.findByText(/inps/i)).toBeInTheDocument();
});

test('SalaryPage shows and submits a stored manual override as the effective net', async () => {
  const user = userEvent.setup();
  let requestBody: unknown;

  server.use(
    http.get('/api/v1/salary', () =>
      HttpResponse.json([{
        id: 'sc1', user_id: 'u1', valid_from: '2026-01-01', ral: 4000,
        employer_contrib_rate: 0.04, voluntary_contrib_rate: 0, regional_tax_rate: 0.0173,
        municipal_tax_rate: 0.001, meal_vouchers_annual: 0, welfare_annual: 0,
        salary_months: 12, manual_net_override: 2750, computed_net_monthly: 2600, effective_net_monthly: 2750,
      }])
    ),
    http.put('/api/v1/salary/sc1', async ({ request }) => {
      requestBody = await request.json();
      return HttpResponse.json({
        id: 'sc1', user_id: 'u1', valid_from: '2026-01-01', ral: 4200,
        employer_contrib_rate: 0.04, voluntary_contrib_rate: 0, regional_tax_rate: 0.0173,
        municipal_tax_rate: 0.001, meal_vouchers_annual: 0, welfare_annual: 0,
        salary_months: 12, manual_net_override: 2750, computed_net_monthly: 2600, effective_net_monthly: 2750,
      });
    })
  );

  render(<SalaryPage />, { wrapper });
  await waitFor(() => expect(screen.getByText(/manual override/i)).toBeInTheDocument());

  await user.click(screen.getByRole('button', { name: /edit/i }));
  await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());

  await user.click(screen.getByRole('button', { name: /^save$/i }));

  await waitFor(() => expect(requestBody).toBeTruthy());
  expect(requestBody).toHaveProperty('manual_net_override', 2750);
});
