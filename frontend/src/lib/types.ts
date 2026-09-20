/** The shapes the API answers with. Every amount arrives as a decimal string. */

export type Currency = 'ARS' | 'USD';
export type TransactionType = 'expense' | 'income';
export type RateType = 'official' | 'blue' | 'mep' | 'ccl' | 'card' | 'manual';
export type ConfirmationStatus = 'estimated' | 'confirmed';
export type BudgetState = 'on_pace' | 'ahead_of_pace' | 'warning' | 'over';
export type NumberFormat = 'comma_decimal' | 'dot_decimal';
export type SignConvention =
  | 'negative_is_expense'
  | 'positive_is_expense'
  | 'debit_credit_columns';
export type RowStatus = 'new' | 'duplicate' | 'ignored' | 'needs_category';
export type ReviewTrigger = 'recurring_monthly' | 'month_end' | 'manual';
export type ReviewStatus = 'queued' | 'running' | 'done' | 'failed';
export type SuggestionKind = 'add_transaction';
export type SuggestionStatus = 'pending' | 'accepted' | 'rejected' | 'expired';

export interface Category {
  id: string;
  name: string;
  color: string;
  icon: string | null;
  is_default: boolean;
  type: TransactionType;
}

export interface Transaction {
  id: string;
  amount: string;
  currency: Currency;
  type: TransactionType;
  category_id: string;
  date: string;
  description: string | null;
  notes: string | null;
  is_fixed: boolean;
  exchange_rate: string | null;
  exchange_rate_type: RateType | null;
  exchange_rate_status: ConfirmationStatus | null;
  amount_status: ConfirmationStatus;
  refund_of_id: string | null;
  installment_purchase_id: string | null;
  installment_number: number | null;
  /** Set when it was recorded by accepting a Recurring Expense's suggestion. */
  recurring_expense_id: string | null;
  import_id: string | null;
  created_at: string;
}

export interface InstallmentPurchase {
  id: string;
  description: string;
  total_amount: string;
  currency: Currency;
  installments: number;
  category_id: string;
  purchase_date: string;
  created_at: string;
  cuotas?: Transaction[];
}

export interface RecurringExpense {
  id: string;
  description: string;
  category_id: string;
  currency: Currency;
  reference_amount: string;
  expected_day: number;
  is_fixed: boolean;
  is_active: boolean;
  created_at: string;
}

export interface BudgetProgress {
  id: string;
  category_id: string;
  amount: string;
  currency: Currency;
  month: string;
  spent: string;
  percentage: string;
  pace: string | null;
  state: BudgetState;
}

export interface CategorySpending {
  category_id: string;
  name: string;
  color: string;
  total: string;
}

export interface MonthlySpending {
  month: string;
  currency: Currency;
  categories: CategorySpending[];
}

export interface MonthlySummary {
  month: string;
  currency: Currency;
  total_income: string;
  total_expenses: string;
  monthly_result: string;
  by_category: CategorySpending[];
  budgets: BudgetProgress[];
  recent: Transaction[];
}

export interface Settings {
  display_currency: Currency;
  default_rate_type: RateType;
}

export interface ColumnMapping {
  date: string;
  description: string;
  amount?: string | null;
  debit?: string | null;
  credit?: string | null;
  currency?: string | null;
  type?: string | null;
}

export interface ImportProfile {
  id: string;
  name: string;
  source: string;
  column_mapping: ColumnMapping;
  date_format: string;
  number_format: NumberFormat;
  sign_convention: SignConvention;
  ignore_patterns: string[];
  created_at: string;
}

export interface CategorizationRule {
  id: string;
  pattern: string;
  category_id: string;
  origin: 'manual' | 'suggestion';
  created_at: string;
}

export interface PreviewRow {
  number: number;
  date: string;
  description: string;
  amount: string;
  currency: Currency;
  type: TransactionType;
  category_id: string | null;
  status: RowStatus;
}

export interface ImportPreview {
  profile_id: string;
  filename: string;
  rows: PreviewRow[];
}

export interface ConfirmRow {
  date: string;
  description: string;
  amount: string;
  currency: Currency;
  type: TransactionType;
  category_id: string | null;
  skip: boolean;
  is_refund: boolean;
  remember: { pattern: string } | null;
}

export interface ImportRecord {
  id: string;
  profile_id: string;
  filename: string;
  imported_count: number;
  skipped_count: number;
  created_at: string;
}

export interface FileColumns {
  filename: string;
  columns: string[];
}

export interface Review {
  id: string;
  trigger: ReviewTrigger;
  status: ReviewStatus;
  used_agent: boolean;
  error: string | null;
  note: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

/** What an `add_transaction` Suggestion would record. */
export interface AddTransactionPayload {
  description: string;
  category_id: string;
  currency: Currency;
  amount: string;
  date: string;
  is_fixed: boolean;
  recurring_expense_id: string;
}

export interface Suggestion {
  id: string;
  review_id: string;
  kind: SuggestionKind;
  month: string;
  payload: AddTransactionPayload;
  rationale: string;
  status: SuggestionStatus;
  rejection_reason: string | null;
  /** What accepting it created, e.g. the Transaction. */
  result_id: string | null;
  expires_on: string;
  resolved_at: string | null;
  created_at: string;
}

export interface Inbox {
  suggestions: Suggestion[];
  pending_count: number;
  /** The Reviews queued or running right now. */
  reviews: Review[];
}
