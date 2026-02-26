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
