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
export interface Account {
  id: string;
  user_id: string;
  type: 'saving' | 'investment' | 'pension';
  name: string;
  opening_balance: number;
  opening_balance_month?: string | null;
  is_active: boolean;
}

export interface AccountCreate {
  type: 'saving' | 'investment' | 'pension';
  name: string;
  opening_balance?: number;
  opening_balance_month?: string;
}

export interface Transfer {
  id: string;
  user_id: string;
  date: string;
  detail: string;
  amount: number;
  from_account_type: 'bank' | 'saving' | 'investment' | 'pension';
  from_account_id: string | null;
  from_payment_method_id: string | null;
  from_account_name: string;
  to_account_type: 'bank' | 'saving' | 'investment' | 'pension';
  to_account_id: string | null;
  to_payment_method_id: string | null;
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
  account_id: string | null;
  computed_amount: number;
  manual_override: number | null;
  final_amount: number;
  valuation_status?: 'estimated' | 'statement_reconciled' | 'manual_reconciled' | 'legacy_reconciled' | null;
  reconciled_as_of_month?: string | null;
  reconciled_balance?: number | null;
  reconciliation_source?: 'statement' | 'manual' | 'legacy_override' | null;
  employee_contributions?: number | null;
  employer_contributions?: number | null;
  tfr_contributions?: number | null;
  net_transfers?: number | null;
  projected_through?: string | null;
}

export interface PensionSnapshot {
  id: string;
  user_id: string;
  account_id: string;
  as_of_month: string;
  balance: number;
  source: 'statement' | 'manual' | 'legacy_override';
  notes: string | null;
}

export interface PensionSnapshotInput {
  account_id: string;
  as_of_month: string;
  balance: number;
  source: 'statement' | 'manual';
  notes: string | null;
}

export interface PensionOpeningBalanceUpdate {
  amount: number;
  month: string;
}

// Salary
export interface SalaryFields {
  ral: number;
  regional_tax_rate: number;
  municipal_tax_rate: number;
  meal_vouchers_annual: number;
  welfare_annual: number;
  salary_months: 12 | 13 | 14;
}

export interface PensionPayrollInputs {
  employee_contrib_rate: number;
  employee_contrib_annual_base: number;
  employer_contrib_rate: number;
  employer_contrib_annual_base: number;
  tfr_contrib_annual: number;
  account_id?: string;
}

export interface SalaryConfig extends SalaryFields {
  id: string;
  user_id: string;
  valid_from: string;
  manual_net_override: number | null;
  computed_net_monthly: number;
  effective_net_monthly: number;
  calculated_as_of: string;
  salary_config_id: string;
  salary_config_valid_from: string;
  pension_config_id: string | null;
  pension_config_valid_from: string | null;
  pension: PensionPayrollBreakdown;
  tax_config_id: string;
  tax_config_valid_from: string;
}

export interface PensionPayrollBreakdown {
  employee_pension_contribution_annual: number;
  employer_pension_contribution_annual: number;
  tfr_contribution_annual: number;
  pension_payroll_deduction_annual: number;
  pension_employer_taxable_excess_annual: number;
  pension_cap_eligible_contributions_annual: number;
  pension_cap_used_annual: number;
  pension_cap_excess_annual: number;
  pension_deductibility_cap: number;
  pension_cap_scope: string;
}

export interface SalaryBreakdown extends PensionPayrollBreakdown {
  gross_annual: number;
  social_security: number;
  tax_config_id: string;
  tax_config_valid_from: string;
  taxable_base: number;
  income_tax_gross: number;
  employment_deduction: number;
  income_tax_net: number;
  regional_surtax: number;
  municipal_surtax: number;
  net_annual: number;
  computed_net_monthly: number;
  meal_vouchers_monthly: number;
  welfare_monthly: number;
  salary_months: 12 | 13 | 14;
  calculated_as_of?: string | null;
  salary_config_id?: string | null;
  salary_config_valid_from?: string | null;
  pension_config_id?: string | null;
  pension_config_valid_from?: string | null;
  manual_net_override?: number | null;
  effective_net_monthly?: number | null;
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
  salary?: SalaryFields & { manual_net_override?: number | null };
  pension?: {
    name: string;
    opening_balance: number;
    opening_balance_month: string;
  } & Omit<PensionPayrollInputs, 'account_id'> & { contribution_periods_by_month: number[] };
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
