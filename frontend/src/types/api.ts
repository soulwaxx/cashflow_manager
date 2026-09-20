// Auth
export interface User {
  id: string;
  email: string | null;
  name: string;
  has_password: boolean;
  has_oidc: boolean;
}

export interface AuthConfig {
  oidc_enabled: boolean;
  basic_auth_enabled: boolean;
}

// Payment Methods
export interface PaymentMethod {
  id: string;
  user_id: string;
  name: string;
  type: 'bank' | 'debit_card' | 'credit_card' | 'revolving' | 'prepaid' | 'cash';
  is_main_bank: boolean;
  linked_bank_id: string | null;
  opening_balance: number | null;
  is_active: boolean;
  has_stamp_duty?: boolean;
}

export interface PaymentMethodUpdate {
  name?: string;
  is_active?: boolean;
  linked_bank_id?: string | null;
  effective_billing_month?: string;
  has_stamp_duty?: boolean;
}

// Categories
export interface Category {
  id: string;
  user_id: string;
  type: string;
  sub_type: string;
  is_active: boolean;
}

// Transactions
export interface Transaction {
  id: string;
  user_id: string;
  date: string;
  detail: string;
  amount: number;
  payment_method_id: string | null;
  category_id: string | null;
  transaction_direction: 'debit' | 'income' | 'credit';
  billing_month: string;
  recurrence_months: number | null;
  parent_transaction_id: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

// Transfers
export interface Transfer {
  id: string;
  user_id: string;
  date: string;
  detail: string;
  amount: number;
  from_account_type: 'bank' | 'saving' | 'investment' | 'pension';
  from_account_name: string;
  to_account_type: 'bank' | 'saving' | 'investment' | 'pension';
  to_account_name: string;
  billing_month: string;
  recurrence_months: number | null;
  parent_transfer_id: string | null;
  notes: string | null;
  created_at: string;
}

// Monthly Summary
export interface MonthlySummary {
  year: number;
  month: number;
  incomes: number;
  outcomes_by_method: Record<string, number>;
  transfers_out_bank: number;
  transfers_in_bank: number;
  bank_balance: number;
  stamp_duty?: number;
}

// Assets
export interface Asset {
  asset_type: 'saving' | 'investment' | 'pension' | 'bank';
  asset_name: string;
  computed_amount: number;
  manual_override: number | null;
  final_amount: number;
}

// Salary
export interface SalaryConfig {
  id: string;
  user_id: string;
  valid_from: string;
  ral: number;
  employer_contrib_rate: number;
  voluntary_contrib_rate: number;
  regional_tax_rate: number;
  municipal_tax_rate: number;
  meal_vouchers_annual: number;
  welfare_annual: number;
  salary_months: number;
  manual_net_override: number | null;
  computed_net_monthly: number;
  effective_net_monthly: number;
}

export interface SalaryBreakdown {
  gross_annual: number;
  social_security: number;
  pension_deductible: number;
  taxable_base: number;
  income_tax_gross: number;
  employment_deduction: number;
  income_tax_net: number;
  regional_surtax: number;
  municipal_surtax: number;
  net_annual: number;
  net_monthly: number;
  meal_vouchers_monthly: number;
  welfare_monthly: number;
}

// Tax Config
export interface TaxConfig {
  id: string;
  valid_from: string;
  inps_rate: number;
  irpef_band1_rate: number;
  irpef_band1_limit: number;
  irpef_band2_rate: number;
  irpef_band2_limit: number;
  irpef_band3_rate: number;
  employment_deduction_band1_limit: number;
  employment_deduction_band1_amount: number;
  employment_deduction_band2_limit: number;
  employment_deduction_band2_base: number;
  employment_deduction_band2_variable: number;
  employment_deduction_band2_range: number;
  employment_deduction_band3_limit: number;
  employment_deduction_band3_base: number;
  employment_deduction_band3_range: number;
  pension_deductibility_cap: number;
  employment_deduction_floor: number;
}

// Analytics
export interface AnalyticsCategoryRow {
  category_id: string;
  type: string;
  sub_type: string;
  month: string;
  total_amount: number;
}

export interface AnalyticsTransferRow {
  to_account_type: string;
  to_account_name: string;
  month: string;
  total_amount: number;
}

// Forecasting
export interface Forecast {
  id: string;
  user_id: string;
  name: string;
  base_year: number;
  projection_years: number;
  created_at: string;
  updated_at: string;
}

export interface ForecastLine {
  id: string;
  detail: string;
  category_id: string | null;
  base_amount: number;
  billing_day: number;
  payment_method_id: string | null;
  notes: string | null;
  adjustments: ForecastLineAdjustment[];
}

export interface ForecastLineRequest {
  detail: string;
  base_amount: number;
  category_id?: string | null;
  payment_method_id?: string | null;
  billing_day?: number;
  notes?: string | null;
}

export interface ForecastLineAdjustment {
  id: string;
  valid_from: string;
  new_amount: number;
  adjustment_type: 'fixed' | 'percentage';
}

export interface ForecastAdjustment extends ForecastLineAdjustment {
  forecast_line_id: string;
}

export interface ForecastProjection {
  forecast_id: string;
  base_year: number;
  projection_years: number;
  period: { from: string; to: string };
  lines: Array<{
    line_id: string;
    detail: string;
    category_id: string | null;
    base_amount: number;
    billing_day: number;
    adjustments: ForecastLineAdjustment[];
    months: Array<{ month: string; effective_amount: number }>;
  }>;
  monthly_totals: Array<{ month: string; total: number }>;
  yearly_totals: Array<{ year: number; total: number }>;
}

// Onboarding
export interface OnboardingPayload {
  tracking_start_date: string;
  main_bank: {
    name: string;
    opening_balance: number;
  };
  additional_banks?: Array<{ name: string; opening_balance: number }>;
  payment_methods?: Array<{
    name: string;
    type: PaymentMethod['type'];
    linked_bank_name?: string;
  }>;
  saving_accounts?: Array<{ name: string; opening_balance: number }>;
  investment_accounts?: Array<{ name: string; opening_balance: number }>;
  salary?: {
    ral: number;
    employer_contrib_rate: number;
    voluntary_contrib_rate: number;
    regional_tax_rate: number;
    municipal_tax_rate: number;
    meal_vouchers_annual: number;
    welfare_annual: number;
    salary_months?: number;
    manual_net_override?: number | null;
  };
}

// User Settings
// The backend stores settings as key/value rows; GET /user-settings returns an array of these.
export interface UserSettingItem {
  user_id: string;
  key: string;
  value: string;
  updated_at: string;
}

export type UserSettings = UserSettingItem[];
