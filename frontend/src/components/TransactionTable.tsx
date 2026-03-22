"use client";
import { Transaction } from "@/types";
import { receiptApi } from "@/lib/api";
import { getAssignedUser } from "@/lib/attribution";
import { useState } from "react";

interface Props {
  orgId: string;
  transactions: Transaction[];
}

const fmt = (val: number) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(Math.abs(val));

export default function TransactionTable({ orgId, transactions }: Props) {
  const [downloading, setDownloading] = useState<string | null>(null);

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
            {["Date", "Description", "Type", "Zelle", "Amount", "Category", "Assigned User", "Receipt"].map((h) => (
              <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-100">
          {transactions.map((tx) => (
            <tr key={tx.id} className="hover:bg-gray-50 transition-colors">
              <td className="px-4 py-3 text-sm text-gray-600 whitespace-nowrap">
                {tx.date?.slice(0, 10)}
              </td>
              <td className="px-4 py-3 text-sm font-medium text-gray-900 max-w-xs">
                <div className="truncate">{tx.name}</div>
                {tx.is_zelle && tx.zelle_counterparty && (
                  <div className="text-xs text-purple-500 mt-0.5 truncate">{tx.zelle_counterparty}</div>
                )}
              </td>
              <td className="px-4 py-3">
                <span
                  className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                    tx.transaction_type === "credit"
                      ? "bg-emerald-100 text-emerald-700"
                      : "bg-red-100 text-red-700"
                  }`}
                >
                  {tx.transaction_type === "credit" ? "Deposit" : "Withdrawal"}
                </span>
              </td>
              <td className="px-4 py-3 text-sm">
                {tx.is_zelle ? (
                  <span className="text-purple-600 font-medium text-xs">
                    Zelle {tx.zelle_direction}
                  </span>
                ) : (
                  <span className="text-gray-300">-</span>
                )}
              </td>
              <td
                className={`px-4 py-3 text-sm font-semibold whitespace-nowrap ${
                  tx.transaction_type === "credit" ? "text-emerald-600" : "text-red-600"
                }`}
              >
                {tx.transaction_type === "credit" ? "+" : "-"}{fmt(tx.amount)}
              </td>
              <td className="px-4 py-3 text-xs text-gray-500">
                {tx.category || "Uncategorized"}
              </td>
              <td className="px-4 py-3">
                {(() => {
                  const user = getAssignedUser(tx);
                  if (user === "Kenny") {
                    return (
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-700">
                        Kenny
                      </span>
                    );
                  }
                  if (user === "Bright") {
                    return (
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-700">
                        Bright
                      </span>
                    );
                  }
                  return <span className="text-gray-300 text-xs">—</span>;
                })()}
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
          ))}
        </tbody>
      </table>
    </div>
  );
}
