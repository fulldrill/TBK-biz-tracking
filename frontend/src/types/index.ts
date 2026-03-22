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

export interface ParseResult {
  transaction_count: number;
  transactions: ParsedTransaction[];
  source_file: string;
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
