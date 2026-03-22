"use client";
import { Transaction } from "@/types";
import { receiptApi, transactionApi } from "@/lib/api";
import { getAssignedUser } from "@/lib/attribution";
import { useState } from "react";

interface Props {
  orgId: string;
  transactions: Transaction[];
  isAdmin?: boolean;
  selectedIds: Set<string>;
  onSelectionChange: (ids: Set<string>) => void;
  onTransactionUpdated: (tx: Transaction) => void;
}

const fmt = (val: number) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(Math.abs(val));

const USERS = ["Kenny", "Bright", "Tony", "—"];

function UserBadge({ user }: { user: string | null }) {
  if (user === "Kenny")
    return <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-700">Kenny</span>;
  if (user === "Bright")
    return <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-700">Bright</span>;
  if (user === "Tony")
    return <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-teal-100 text-teal-700">Tony</span>;
  return <span className="text-gray-300 text-xs">—</span>;
}

export default function TransactionTable({
  orgId,
  transactions,
  isAdmin,
  selectedIds,
  onSelectionChange,
  onTransactionUpdated,
}: Props) {
  const [downloading, setDownloading] = useState<string | null>(null);
  const [patching, setPatching] = useState<string | null>(null);

  const allSelected = transactions.length > 0 && transactions.every((t) => selectedIds.has(t.id));

  const toggleAll = () => {
    if (allSelected) {
      const next = new Set(selectedIds);
      transactions.forEach((t) => next.delete(t.id));
      onSelectionChange(next);
    } else {
      const next = new Set(selectedIds);
      transactions.forEach((t) => next.add(t.id));
      onSelectionChange(next);
    }
  };

  const toggleOne = (id: string) => {
    const next = new Set(selectedIds);
    next.has(id) ? next.delete(id) : next.add(id);
    onSelectionChange(next);
  };

  const downloadReceipt = async (id: string, name: string) => {
    setDownloading(id);
    try {
      const res = await receiptApi.downloadSingle(orgId, id);
      const url = URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `receipt_${name.replace(/\s/g, "_")}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      alert("Failed to download receipt");
    } finally {
      setDownloading(null);
    }
  };

  const handleAssignUser = async (tx: Transaction, value: string) => {
    setPatching(tx.id);
    try {
      const assigned_user = value === "—" ? null : value;
      const res = await transactionApi.patch(orgId, tx.id, { assigned_user });
      onTransactionUpdated(res.data as Transaction);
    } catch {
      alert("Failed to update assignment");
    } finally {
      setPatching(null);
    }
  };

  if (transactions.length === 0) {
    return (
      <div className="text-center py-16 text-gray-400 border-2 border-dashed rounded-xl">
        <p className="text-lg">No transactions found</p>
        <p className="text-sm mt-1">Connect a bank account and sync to get started</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-gray-200 shadow-sm">
      <table className="min-w-full divide-y divide-gray-200">
        <thead className="bg-gray-50">
          <tr>
            {isAdmin && (
              <th className="px-4 py-3 w-8">
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={toggleAll}
                  className="rounded border-gray-300 text-blue-600"
                />
              </th>
            )}
            {["Date", "Description", "Type", "Zelle", "Amount", "Category", "Assigned", "Receipt"].map((h) => (
              <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-100">
          {transactions.map((tx) => {
            const computedUser = tx.assigned_user ?? getAssignedUser(tx);
            const isSelected = selectedIds.has(tx.id);
            return (
              <tr key={tx.id} className={`hover:bg-gray-50 transition-colors ${isSelected ? "bg-blue-50" : ""}`}>
                {isAdmin && (
                  <td className="px-4 py-3">
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleOne(tx.id)}
                      className="rounded border-gray-300 text-blue-600"
                    />
                  </td>
                )}
                <td className="px-4 py-3 text-sm text-gray-600 whitespace-nowrap">
                  {tx.date?.slice(0, 10)}
                </td>
                <td className="px-4 py-3 text-sm font-medium text-gray-900 max-w-xs">
                  <div className="flex items-center gap-1.5">
                    <div className="truncate">{tx.name}</div>
                    {tx.source === "statement_import" && (
                      <span className="shrink-0 text-xs text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded">imported</span>
                    )}
                  </div>
                  {tx.is_zelle && tx.zelle_counterparty && (
                    <div className="text-xs text-purple-500 mt-0.5 truncate">{tx.zelle_counterparty}</div>
                  )}
                </td>
                <td className="px-4 py-3">
                  <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                    tx.transaction_type === "credit" ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700"
                  }`}>
                    {tx.transaction_type === "credit" ? "Deposit" : "Withdrawal"}
                  </span>
                </td>
                <td className="px-4 py-3 text-sm">
                  {tx.is_zelle ? (
                    <span className="text-purple-600 font-medium text-xs">Zelle {tx.zelle_direction}</span>
                  ) : (
                    <span className="text-gray-300">-</span>
                  )}
                </td>
                <td className={`px-4 py-3 text-sm font-semibold whitespace-nowrap ${
                  tx.transaction_type === "credit" ? "text-emerald-600" : "text-red-600"
                }`}>
                  {tx.transaction_type === "credit" ? "+" : "-"}{fmt(tx.amount)}
                </td>
                <td className="px-4 py-3 text-xs text-gray-500">
                  {tx.category || "Uncategorized"}
                </td>
                <td className="px-4 py-3">
                  {isAdmin ? (
                    <select
                      value={tx.assigned_user ?? "—"}
                      onChange={(e) => handleAssignUser(tx, e.target.value)}
                      disabled={patching === tx.id}
                      className="text-xs border border-gray-200 rounded-lg px-2 py-1 focus:outline-none focus:ring-1 focus:ring-blue-400 disabled:opacity-50 bg-white"
                    >
                      {USERS.map((u) => (
                        <option key={u} value={u}>{u}</option>
                      ))}
                    </select>
                  ) : (
                    <UserBadge user={computedUser} />
                  )}
                </td>
                <td className="px-4 py-3">
                  <button
                    onClick={() => downloadReceipt(tx.id, tx.name || "transaction")}
                    disabled={downloading === tx.id}
                    className="text-blue-500 hover:text-blue-700 text-xs font-medium disabled:opacity-50"
                  >
                    {downloading === tx.id ? "..." : "PDF"}
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
