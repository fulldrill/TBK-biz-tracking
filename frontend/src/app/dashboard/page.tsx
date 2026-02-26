"use client";
import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { transactionApi, totalsApi, receiptApi } from "@/lib/api";
import { Transaction, Totals } from "@/types";
import TransactionTable from "@/components/TransactionTable";
import SummaryCards from "@/components/SummaryCards";
import PlaidLinkButton from "@/components/PlaidLink";

export default function Dashboard() {
  const router = useRouter();
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [totals, setTotals] = useState<Totals | null>(null);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState("");
  const [filters, setFilters] = useState({
    is_zelle: "" as "" | "true" | "false",
    transaction_type: "",
    start_date: "",
    end_date: "",
    category: "",
  });

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = { limit: 300 };
      if (filters.is_zelle === "true") params.is_zelle = true;
      if (filters.is_zelle === "false") params.is_zelle = false;
      if (filters.transaction_type) params.transaction_type = filters.transaction_type;
      if (filters.start_date) params.start_date = filters.start_date;
      if (filters.end_date) params.end_date = filters.end_date;
      if (filters.category) params.category = filters.category;

      const [txRes, totalsRes] = await Promise.all([
        transactionApi.list(params),
        totalsApi.getSummary(filters.start_date || undefined, filters.end_date || undefined),
      ]);
      setTransactions(txRes.data);
      setTotals(totalsRes.data);
    } catch {
      console.error("Load failed");
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    if (typeof window !== "undefined" && !localStorage.getItem("access_token")) {
      router.push("/auth");
      return;
    }
    loadData();
  }, [loadData, router]);

  const handleSync = async () => {
    setSyncing(true);
    setSyncMessage("Syncing transactions in background...");
    try {
      await transactionApi.sync(90);
      setSyncMessage("Sync started. Refreshing in 5 seconds...");
      setTimeout(() => {
        loadData();
        setSyncMessage("");
      }, 5000);
    } catch {
      setSyncMessage("Sync failed. Make sure your bank account is connected.");
    } finally {
      setSyncing(false);
    }
  };

  const handleBatchDownload = async () => {
    try {
      const res = await receiptApi.downloadBatch(
        filters.start_date || undefined,
        filters.end_date || undefined
      );
      const url = URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `biztrack_batch_receipts.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      alert("No transactions to export, or export failed.");
    }
  };

  const handleLogout = () => {
    localStorage.removeItem("access_token");
    router.push("/auth");
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900">BizTrack Receipts</h1>
            <p className="text-xs text-gray-400 mt-0.5">Business Financial Tracking</p>
          </div>
          <div className="flex items-center gap-3">
            <PlaidLinkButton onSuccess={handleSync} />
            <button
              onClick={handleSync}
              disabled={syncing}
              className="bg-gray-800 text-white px-4 py-2 rounded-lg hover:bg-gray-900 text-sm font-medium disabled:opacity-50 transition"
            >
              {syncing ? "Syncing..." : "Sync (90 days)"}
            </button>
            <button
              onClick={handleBatchDownload}
              className="bg-emerald-600 text-white px-4 py-2 rounded-lg hover:bg-emerald-700 text-sm font-medium transition"
            >
              Export PDF
            </button>
            <button
              onClick={handleLogout}
              className="text-gray-500 hover:text-gray-700 text-sm transition"
            >
              Sign out
            </button>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-6">
        {syncMessage && (
          <div className="bg-blue-50 border border-blue-200 text-blue-700 text-sm rounded-xl px-4 py-3 mb-4">
            {syncMessage}
          </div>
        )}

        {/* Totals */}
        {totals && <SummaryCards totals={totals} />}

        {/* Filters */}
        <div className="bg-white border rounded-xl p-4 mb-4">
          <p className="text-xs font-semibold text-gray-500 uppercase mb-3">Filters</p>
          <div className="flex flex-wrap gap-3">
            <div>
              <label className="text-xs text-gray-500 block mb-1">Start Date</label>
              <input
                type="date"
                value={filters.start_date}
                onChange={(e) => setFilters((f) => ({ ...f, start_date: e.target.value }))}
                className="border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="text-xs text-gray-500 block mb-1">End Date</label>
              <input
                type="date"
                value={filters.end_date}
                onChange={(e) => setFilters((f) => ({ ...f, end_date: e.target.value }))}
                className="border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="text-xs text-gray-500 block mb-1">Type</label>
              <select
                value={filters.transaction_type}
                onChange={(e) => setFilters((f) => ({ ...f, transaction_type: e.target.value }))}
                className="border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="">All</option>
                <option value="debit">Withdrawals</option>
                <option value="credit">Deposits</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-500 block mb-1">Zelle</label>
              <select
                value={filters.is_zelle}
                onChange={(e) => setFilters((f) => ({ ...f, is_zelle: e.target.value as "" | "true" | "false" }))}
                className="border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="">All</option>
                <option value="true">Zelle Only</option>
                <option value="false">Non-Zelle</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-500 block mb-1">Category</label>
              <input
                type="text"
                placeholder="Search category..."
                value={filters.category}
                onChange={(e) => setFilters((f) => ({ ...f, category: e.target.value }))}
                className="border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div className="flex items-end">
              <button
                onClick={loadData}
                className="bg-blue-600 text-white px-4 py-1.5 rounded-lg text-sm hover:bg-blue-700 transition"
              >
                Apply
              </button>
            </div>
            <div className="flex items-end">
              <button
                onClick={() => {
                  setFilters({ is_zelle: "", transaction_type: "", start_date: "", end_date: "", category: "" });
                }}
                className="text-gray-500 hover:text-gray-700 px-3 py-1.5 text-sm transition"
              >
                Clear
              </button>
            </div>
          </div>
        </div>

        {/* Transaction count */}
        <div className="flex items-center justify-between mb-3">
          <p className="text-sm text-gray-500">
            {transactions.length} transactions
            {totals && ` | ${totals.transaction_count} total in period`}
          </p>
        </div>

        {loading ? (
          <div className="flex justify-center py-16">
            <div className="animate-pulse text-gray-400">Loading transactions...</div>
          </div>
        ) : (
          <TransactionTable transactions={transactions} />
        )}
      </div>
    </div>
  );
}
