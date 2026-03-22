import { Transaction } from "@/types";

const WALK_IN_KEYWORDS = [
  "walk-in",
  "walk in",
  "walkin",
  "cash deposit",
  "counter deposit",
  "teller deposit",
  "branch deposit",
];

// Names that identify Kenny in transaction descriptions / Zelle counterparty fields
const KENNY_KEYWORDS = ["kenneth", "kenny", "manjo"];

function isKennyZelle(tx: Transaction): boolean {
  const counterparty = (tx.zelle_counterparty ?? "").toLowerCase();
  const name = (tx.name ?? "").toLowerCase();
  return KENNY_KEYWORDS.some((k) => counterparty.includes(k) || name.includes(k));
}

export function getAssignedUser(tx: Transaction): string {
  if (tx.is_zelle) {
    return isKennyZelle(tx) ? "Kenny" : "Bright";
  }

  const name = (tx.name ?? "").toLowerCase();
  if (
    tx.transaction_type === "credit" &&
    WALK_IN_KEYWORDS.some((k) => name.includes(k))
  ) {
    return "Bright";
  }

  if (tx.transaction_type === "debit") return "Kenny";

  return "—";
}

export function exportToCSV(
  transactions: Transaction[],
  filename = "clerq_transactions.csv"
) {
  const header = ["Date", "Description", "Amount", "Category", "Zelle", "Assigned User"];

  const rows = transactions.map((tx) => {
    const amount =
      tx.transaction_type === "credit"
        ? tx.amount.toFixed(2)
        : (-Math.abs(tx.amount)).toFixed(2);
    const desc = `"${(tx.name ?? "").replace(/"/g, '""')}"`;
    const counterparty = tx.is_zelle && tx.zelle_counterparty
      ? ` (${tx.zelle_counterparty})`
      : "";
    return [
      tx.date?.slice(0, 10) ?? "",
      `"${(tx.name ?? "").replace(/"/g, '""')}${counterparty}"`,
      amount,
      `"${(tx.category ?? "Uncategorized").replace(/"/g, '""')}"`,
      tx.is_zelle ? "Y" : "N",
      getAssignedUser(tx),
    ];
  });

  const csv = [header, ...rows].map((r) => r.join(",")).join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
