/** The shapes the API answers with. Every amount arrives as a decimal string. */

export type Currency = 'ARS' | 'USD';
export type TransactionType = 'expense' | 'income';
export type RateType = 'official' | 'blue' | 'mep' | 'ccl' | 'card' | 'manual';
export type ConfirmationStatus = 'estimated' | 'confirmed';
export type AgentLookback = 'quarter' | 'year';
export type BudgetState = 'on_pace' | 'ahead_of_pace' | 'warning' | 'over';
export type NumberFormat = 'comma_decimal' | 'dot_decimal';
export type SignConvention =
  | 'negative_is_expense'
  | 'positive_is_expense'
  | 'debit_credit_columns';
export type RowStatus = 'new' | 'duplicate' | 'ignored' | 'needs_category';
export type ReviewTrigger =
  | 'recurring_monthly'
  | 'month_end'
  | 'manual'
  | 'manual_agent';
export type ReviewStatus = 'queued' | 'running' | 'done' | 'failed';
export type SuggestionKind = 'add_transaction' | 'set_budget';
export type SuggestionStatus = 'pending' | 'accepted' | 'rejected' | 'expired';
export type IndexOrigin = 'api' | 'manual';

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

/** How a Recurring Expense's amount moves: every N months, by this much. */
export interface AdjustmentRule {
  kind: 'percentage' | 'index';
  period_months: number;
  /** The month the cycle counts from, as its first day. */
  start_month: string;
  /** Percentage points, for a percentage rule: "10.00" raises it by 10%. */
  percentage: string | null;
  /** The Inflation Index it follows, for an index rule. */
  index_name: string | null;
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
  adjustment: AdjustmentRule | null;
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
  /** How far back a Review may read: the month it is about, and before it. */
  agent_lookback: AgentLookback;
}

/** How much prices moved in one month, in percentage points: 1.659 is 1.659%. */
export interface InflationIndex {
  id: string;
  name: string;
  /** The month it describes, as its first day. */
  month: string;
  value: string;
  source: IndexOrigin;
  updated_at: string;
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
  /** The month the run is about, as its first day. */
  month: string;
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

/** What a `set_budget` Suggestion would set. */
export interface SetBudgetPayload {
  category_id: string;
  month: string;
  amount: string;
  currency: Currency;
}

/** A Transaction that may already be the payment a Suggestion proposes. */
export interface PossibleMatch {
  id: string;
  description: string | null;
  amount: string;
  currency: Currency;
  date: string;
}

interface ProposedChange {
  id: string;
  review_id: string;
  month: string;
  rationale: string;
  status: SuggestionStatus;
  rejection_reason: string | null;
  /** What accepting it created, e.g. the Transaction or the Budget. */
  result_id: string | null;
  expires_on: string;
  resolved_at: string | null;
  created_at: string;
}

/**
 * A proposal waiting in the Inbox.
 *
 * The kind says which payload it carries, so a card that has checked the kind
 * knows exactly which fields it can read.
 */
export type Suggestion =
  | (ProposedChange & { kind: 'add_transaction'; payload: AddTransactionPayload })
  | (ProposedChange & { kind: 'set_budget'; payload: SetBudgetPayload });

/**
 * A proposal as the Inbox hands it over, with its Possible Match.
 *
 * Only the Inbox answers this, because the match is about the Transactions of
 * the moment it was read; accepting and rejecting hand back the proposal alone.
 */
export type InboxSuggestion = Suggestion & {
  /**
   * An Expense already recorded that may be this same payment. A hint only:
   * the proposal is pending whether or not one was found.
   */
  possible_match: PossibleMatch | null;
};

/** The fields of a proposal the user changed before accepting it. */
export type SuggestionEdits =
  | Partial<AddTransactionPayload>
  | Partial<SetBudgetPayload>;

/**
 * A read-only observation the agent recorded during a Review.
 *
 * There is nothing to accept: the only thing to do with one is read it and say
 * so, which is what dismissing records. It waits in the Inbox during its month
 * and stays as history afterwards.
 */
export interface Insight {
  id: string;
  review_id: string;
  /** The month it is about, as its first day. */
  month: string;
  topic: string;
  body: string;
  dismissed_at: string | null;
  created_at: string;
}

export interface Inbox {
  suggestions: InboxSuggestion[];
  pending_count: number;
  /** This month's observations the user has not dismissed yet. */
  insights: Insight[];
  /** The Reviews queued or running right now. */
  reviews: Review[];
}
