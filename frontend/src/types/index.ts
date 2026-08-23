export interface Transaction {
  id: string;
  plaid_transaction_id: string;
  amount: number;
  date: string;
  name: string | null;
  category: string | null;
  transaction_type: "debit" | "credit";
  is_zelle: boolean;
  zelle_counterparty: string | null;
  zelle_direction: "sent" | "received" | null;
  receipt_path: string | null;
  assigned_user: string | null;
  source: "plaid" | "statement_import";
  repayment_loan_id?: string | null;
  business_purpose?: string | null;
  /** derived | ai | manual | needs_input */
  purpose_source?: string | null;
}

// --- Loan types ---

export type LoanStatus = "active" | "paid_off" | "written_off";

export interface LoanRepayment {
  id: string;
  loan_id: string;
  amount: number;
  date: string;
  notes: string | null;
  transaction_id: string | null;
  created_at: string;
}

export interface Loan {
  id: string;
  org_id: string;
  borrower_name: string;
  principal: number;
  date_issued: string;
  notes: string | null;
  status: LoanStatus;
  created_at: string;
  outstanding_balance: number;
  repayments: LoanRepayment[];
}

export interface LoanSummary {
  total_loaned: number;
  total_repaid: number;
  total_outstanding: number;
  active_loan_count: number;
}

/** A transaction returned by the /statements/parse endpoint (not yet saved to DB). */
export interface ParsedTransaction {
  date: string;
  name: string;
  amount: number;
  transaction_type: "debit" | "credit";
  is_zelle: boolean;
  zelle_counterparty: string | null;
  zelle_direction: "sent" | "received" | null;
  category: string | null;
  assigned_user: string | null;
  statement_file?: string;
}

export interface StatementFileReport {
  file: string;
  /** "text" when read from the PDF's text layer, "vision" when OCR'd. */
  method?: "text" | "vision";
  pages: number;
  transactions: number;
  failed_pages: { page: number; error: string }[];
  /** True when the extracted totals matched the statement's own printed totals. */
  reconciled?: boolean;
  period_end?: string | null;
  months: string[];
}

export interface ParseResult {
  transaction_count: number;
  transactions: ParsedTransaction[];
  source_file: string;
  file_reports: StatementFileReport[];
  problem_files: StatementFileReport[];
  months_covered: string[];
}

export interface Totals {
  total_deposits: number;
  total_withdrawals: number;
  zelle_sent: number;
  zelle_received: number;
  net_balance: number;
  transaction_count: number;
  period_start: string;
  period_end: string;
}

// --- Profit & Loss types ---

export interface PnlLine {
  label: string;
  amount: number;
  count: number;
  /** True when the line comes from a manual entry rather than bank data. */
  manual: boolean;
  /** True when the user removed this line from the statement. */
  user_excluded?: boolean;
  /** Which section it came from, present only on user-excluded lines. */
  section?: "revenue" | "expense";
  /** Keyed "YYYY-MM" for every month in the period. */
  monthly: Record<string, number>;
}

export type PnlEntryType = "revenue" | "expense";
export type PnlRecurrence = "monthly" | "once";

export interface PnlEntry {
  id: string;
  org_id: string;
  label: string;
  amount: number;
  entry_type: PnlEntryType;
  recurrence: PnlRecurrence;
  start_date: string;
  end_date: string | null;
  notes: string | null;
  is_active: boolean;
  created_at: string;
}

export interface OrgPerson {
  id: string;
  org_id: string;
  name: string;
  /** Comma-separated other names this person appears under on statements. */
  aliases?: string | null;
}

export interface PnlMonth {
  month: string;
  revenue: number;
  expenses: number;
  net: number;
}

export interface PnlStatement {
  period_start: string;
  period_end: string;
  basis: string;
  months: string[];
  revenue_lines: PnlLine[];
  total_revenue: number;
  expense_lines: PnlLine[];
  total_expenses: number;
  net_profit: number;
  margin_pct: number;
  excluded_lines: PnlLine[];
  total_excluded: number;
  monthly_summary: PnlMonth[];
  transaction_count: number;
  manual_entry_count: number;
  /** How many rows were shifted to the month they were earned. */
  deferred_count: number;
  /** Months with no bank activity — almost always a missing statement. */
  empty_months: string[];
}

export interface BankAccount {
  id: string;
  account_name: string;
  account_type: string;
  institution_name: string;
  last_synced: string | null;
}

export interface MonthlyBreakdown {
  [key: string]: {
    deposits: number;
    withdrawals: number;
    zelle_sent: number;
    zelle_received: number;
    count: number;
  };
}

// --- Organization types ---

export type OrgRole = "admin" | "viewer";

export interface Organization {
  id: string;
  name: string;
  slug: string;
  owner_id: string;
  created_at: string;
}

export interface UserOrg {
  org: Organization;
  role: OrgRole;
  member_count: number;
}

export interface OrgMember {
  user_id: string;
  email: string;
  full_name: string | null;
  role: OrgRole;
  joined_at: string;
}

export interface OrgInvite {
  id: string;
  org_id: string;
  token: string;
  role: OrgRole;
  expires_at: string;
  used_by: string | null;
  is_active: boolean;
}

export interface InvitePreview {
  org_name: string;
  org_id: string;
  role: OrgRole;
  expires_at: string;
}
