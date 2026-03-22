"use client";
import { useState, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import { statementApi } from "@/lib/api";
import { exportToCSV } from "@/lib/attribution";
import { ParsedTransaction, ParseResult } from "@/types";
import { useOrg } from "@/context/OrgContext";

const fmt = (val: number) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(val);

function UserBadge({ user }: { user: string | null }) {
  if (user === "Kenny")
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-700">
        Kenny
      </span>
    );
  if (user === "Bright")
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-700">
        Bright
      </span>
    );
  return <span className="text-gray-300 text-xs">—</span>;
}

export default function StatementsPage() {
  const router = useRouter();
  const { activeOrg, isAdmin } = useOrg();
  const orgId = activeOrg?.org.id;

  const [dragging, setDragging] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [parsing, setParsing] = useState(false);
  const [parseResult, setParseResult] = useState<ParseResult | null>(null);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<{ inserted: number; skipped: number } | null>(null);
  const [error, setError] = useState("");

  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = (f: File) => {
    setFile(f);
    setParseResult(null);
    setImportResult(null);
    setError("");
  };

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      const dropped = e.dataTransfer.files[0];
      if (dropped) handleFile(dropped);
    },
    []
  );

  const handleParse = async () => {
    if (!file || !orgId) return;
    setParsing(true);
    setError("");
    setParseResult(null);
    setImportResult(null);

    try {
      const res = await statementApi.parse(orgId, file);
      setParseResult(res.data as ParseResult);
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Parsing failed. Check your OpenAI API key and try again.";
      setError(msg);
    } finally {
      setParsing(false);
    }
  };

  const handleImport = async () => {
    if (!parseResult || !orgId) return;
    setImporting(true);
    setError("");

    try {
      const res = await statementApi.import(orgId, parseResult.transactions);
      setImportResult(res.data);
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Import failed. Please try again.";
      setError(msg);
    } finally {
      setImporting(false);
    }
  };

  const handleExportCSV = () => {
    if (!parseResult) return;
    // Map ParsedTransaction to a shape compatible with exportToCSV
    const mapped = parseResult.transactions.map((tx) => ({
      id: "",
      plaid_transaction_id: "",
      amount: tx.amount,
      date: tx.date,
      name: tx.name,
      category: tx.category,
      transaction_type: tx.transaction_type,
      is_zelle: tx.is_zelle,
      zelle_counterparty: tx.zelle_counterparty,
      zelle_direction: tx.zelle_direction,
      receipt_path: null,
      assigned_user: tx.assigned_user,
      source: "statement_import" as const,
    }));
    exportToCSV(mapped, `clerq_statement_${parseResult.source_file.replace(/\.[^.]+$/, "")}.csv`);
  };

  if (!isAdmin) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <p className="text-gray-400">Admin access required to upload statements.</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b px-6 py-4">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900">Statement Parser</h1>
            <p className="text-xs text-gray-400 mt-0.5">
              Upload a PDF bank statement — AI extracts all transactions
            </p>
          </div>
          <button
            onClick={() => router.push("/dashboard")}
            className="text-gray-500 hover:text-gray-700 text-sm transition"
          >
            ← Back to Dashboard
          </button>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-6 py-8 space-y-6">
        {/* Upload zone */}
        <div
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => inputRef.current?.click()}
          className={`border-2 border-dashed rounded-2xl p-10 text-center cursor-pointer transition-colors ${
            dragging
              ? "border-blue-400 bg-blue-50"
              : file
              ? "border-emerald-400 bg-emerald-50"
              : "border-gray-300 bg-white hover:border-blue-300 hover:bg-blue-50"
          }`}
        >
          <input
            ref={inputRef}
            type="file"
            accept=".pdf,.zip"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) handleFile(f);
            }}
          />
          <div className="text-4xl mb-3">
            {file ? "📄" : "📂"}
          </div>
          {file ? (
            <>
              <p className="font-semibold text-gray-900">{file.name}</p>
              <p className="text-sm text-gray-500 mt-1">
                {(file.size / 1024).toFixed(0)} KB — click to replace
              </p>
            </>
          ) : (
            <>
              <p className="font-semibold text-gray-700">
                Drop a PDF or ZIP here, or click to browse
              </p>
              <p className="text-sm text-gray-400 mt-1">
                Supports single PDFs or a ZIP of multiple monthly statements · Max 50 MB
              </p>
            </>
          )}
        </div>

        {/* Parse button */}
        {file && !parseResult && !importResult && (
          <div className="flex justify-center">
            <button
              onClick={handleParse}
              disabled={parsing}
              className="bg-blue-600 text-white px-8 py-3 rounded-xl font-semibold hover:bg-blue-700 disabled:opacity-60 transition flex items-center gap-2"
            >
              {parsing ? (
                <>
                  <span className="animate-spin inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full" />
                  Extracting with AI…
                </>
              ) : (
                "Extract Transactions"
              )}
            </button>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 text-sm">
            {error}
          </div>
        )}

        {/* Import success */}
        {importResult && (
          <div className="bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-xl px-5 py-4">
            <p className="font-semibold">Import complete</p>
            <p className="text-sm mt-1">
              {importResult.inserted} transaction(s) added to your dashboard.
              {importResult.skipped > 0 && ` ${importResult.skipped} duplicate(s) skipped.`}
            </p>
            <button
              onClick={() => router.push("/dashboard")}
              className="mt-3 bg-emerald-600 text-white px-4 py-1.5 rounded-lg text-sm hover:bg-emerald-700 transition"
            >
              Go to Dashboard
            </button>
          </div>
        )}

        {/* Preview table */}
        {parseResult && !importResult && (
          <div className="space-y-4">
            {/* Summary + action bar */}
            <div className="flex items-center justify-between">
              <div>
                <p className="font-semibold text-gray-900">
                  {parseResult.transaction_count} transaction
                  {parseResult.transaction_count !== 1 ? "s" : ""} extracted
                </p>
                <p className="text-xs text-gray-400 mt-0.5">
                  from {parseResult.source_file} — review before importing
                </p>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={handleExportCSV}
                  className="bg-violet-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-violet-700 transition"
                >
                  Export CSV
                </button>
                <button
                  onClick={handleImport}
                  disabled={importing}
                  className="bg-emerald-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-emerald-700 disabled:opacity-60 transition flex items-center gap-2"
                >
                  {importing ? (
                    <>
                      <span className="animate-spin inline-block w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full" />
                      Importing…
                    </>
                  ) : (
                    "Import to Dashboard"
                  )}
                </button>
              </div>
            </div>

            {/* Breakdown badges */}
            <div className="flex gap-3 flex-wrap text-sm">
              {[
                {
                  label: "Deposits",
                  count: parseResult.transactions.filter((t) => t.transaction_type === "credit").length,
                  cls: "bg-emerald-100 text-emerald-700",
                },
                {
                  label: "Withdrawals",
                  count: parseResult.transactions.filter((t) => t.transaction_type === "debit").length,
                  cls: "bg-red-100 text-red-700",
                },
                {
                  label: "Zelle",
                  count: parseResult.transactions.filter((t) => t.is_zelle).length,
                  cls: "bg-purple-100 text-purple-700",
                },
                {
                  label: "Kenny",
                  count: parseResult.transactions.filter((t) => t.assigned_user === "Kenny").length,
                  cls: "bg-blue-100 text-blue-700",
                },
                {
                  label: "Bright",
                  count: parseResult.transactions.filter((t) => t.assigned_user === "Bright").length,
                  cls: "bg-amber-100 text-amber-700",
                },
              ].map(({ label, count, cls }) => (
                <span key={label} className={`px-3 py-1 rounded-full text-xs font-medium ${cls}`}>
                  {label}: {count}
                </span>
              ))}
            </div>

            {/* Table */}
            <div className="overflow-x-auto rounded-xl border border-gray-200 shadow-sm">
              <table className="min-w-full divide-y divide-gray-200 text-sm">
                <thead className="bg-gray-50">
                  <tr>
                    {["Date", "Description", "Type", "Zelle", "Amount", "Category", "Assigned"].map((h) => (
                      <th
                        key={h}
                        className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide"
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-100">
                  {parseResult.transactions.map((tx: ParsedTransaction, i) => (
                    <tr key={i} className="hover:bg-gray-50 transition-colors">
                      <td className="px-4 py-2.5 text-gray-600 whitespace-nowrap">{tx.date}</td>
                      <td className="px-4 py-2.5 font-medium text-gray-900 max-w-xs">
                        <div className="truncate">{tx.name}</div>
                        {tx.is_zelle && tx.zelle_counterparty && (
                          <div className="text-xs text-purple-500 mt-0.5">{tx.zelle_counterparty}</div>
                        )}
                      </td>
                      <td className="px-4 py-2.5">
                        <span
                          className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                            tx.transaction_type === "credit"
                              ? "bg-emerald-100 text-emerald-700"
                              : "bg-red-100 text-red-700"
                          }`}
                        >
                          {tx.transaction_type === "credit" ? "Deposit" : "Withdrawal"}
                        </span>
                      </td>
                      <td className="px-4 py-2.5">
                        {tx.is_zelle ? (
                          <span className="text-purple-600 font-medium text-xs">
                            Zelle {tx.zelle_direction}
                          </span>
                        ) : (
                          <span className="text-gray-300">—</span>
                        )}
                      </td>
                      <td
                        className={`px-4 py-2.5 font-semibold whitespace-nowrap ${
                          tx.transaction_type === "credit" ? "text-emerald-600" : "text-red-600"
                        }`}
                      >
                        {tx.transaction_type === "credit" ? "+" : "−"}{fmt(tx.amount)}
                      </td>
                      <td className="px-4 py-2.5 text-xs text-gray-500">
                        {tx.category || "—"}
                      </td>
                      <td className="px-4 py-2.5">
                        <UserBadge user={tx.assigned_user} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
