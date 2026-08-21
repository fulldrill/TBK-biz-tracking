"use client";
import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { reportApi, getErrorMessage } from "@/lib/api";
import { PnlStatement, PnlLine } from "@/types";
import { useOrg } from "@/context/OrgContext";

const fmt = (val: number) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(val);

/** Accounting convention: negatives in parentheses, matching the PDF. */
const fmtAcct = (val: number) => (val < 0 ? `(${fmt(Math.abs(val))})` : fmt(val));

const monthLabel = (key: string, multiYear: boolean) => {
  const [y, m] = key.split("-");
  const d = new Date(Number(y), Number(m) - 1, 1);
  return d.toLocaleString("en-US", { month: "short" }) + (multiYear ? ` ${y.slice(2)}` : "");
};

export default function PnlPage() {
  const router = useRouter();
  const { activeOrg, isLoading: orgLoading } = useOrg();
  const orgId = activeOrg?.org.id;

  const [years, setYears] = useState<number[]>([]);
  const [year, setYear] = useState<number | null>(null);
  const [useCustom, setUseCustom] = useState(false);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [pnl, setPnl] = useState<PnlStatement | null>(null);
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState("");

  const activeParams = useCallback(() => {
    if (useCustom) {
      return {
        start_date: startDate || undefined,
        end_date: endDate || undefined,
      };
    }
    return { year: year ?? undefined };
  }, [useCustom, startDate, endDate, year]);

  const load = useCallback(async () => {
    if (!orgId) return;
    if (!useCustom && !year) return;
    setLoading(true);
    setError("");
    try {
      const res = await reportApi.pnl(orgId, activeParams());
      setPnl(res.data);
    } catch (err) {
      setError(getErrorMessage(err));
      setPnl(null);
    } finally {
      setLoading(false);
    }
  }, [orgId, year, useCustom, activeParams]);

  // Populate the year picker, defaulting to the most recent year with data.
  useEffect(() => {
    if (typeof window !== "undefined" && !localStorage.getItem("access_token")) {
      router.push("/auth");
      return;
    }
    if (orgLoading) return;
    if (!activeOrg) {
      router.push("/orgs");
      return;
    }
    if (!orgId) return;
    reportApi
      .years(orgId)
      .then((res) => {
        const list: number[] = res.data.years ?? [];
        setYears(list);
        setYear((prev) => prev ?? list[0] ?? new Date().getFullYear());
      })
      .catch(() => {
        const now = new Date().getFullYear();
        setYears([now]);
        setYear((prev) => prev ?? now);
      });
  }, [orgId, activeOrg, orgLoading, router]);

  useEffect(() => {
    load();
  }, [load]);

  const handleDownload = async () => {
    if (!orgId) return;
    setDownloading(true);
    setError("");
    try {
      const res = await reportApi.pnlPdf(orgId, activeParams());
      const url = URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `profit-and-loss_${useCustom ? `${startDate}_${endDate}` : year}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      setError("No transactions in this period, or the export failed.");
    } finally {
      setDownloading(false);
    }
  };

  const multiYear = pnl ? new Set(pnl.months.map((m) => m.slice(0, 4))).size > 1 : false;
  const hasData = pnl && pnl.transaction_count > 0;

  if (orgLoading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="animate-pulse text-gray-400">Loading...</div>
      </div>
    );
  }

  const renderLines = (lines: PnlLine[], emptyText: string) =>
    lines.length > 0 ? (
      lines.map((line) => (
        <tr key={line.label} className="border-b last:border-0">
          <td className="py-2 pl-6 pr-4 text-gray-700">{line.label}</td>
          <td className="py-2 pr-4 text-right text-gray-400 text-xs">{line.count}</td>
          <td className="py-2 pr-4 text-right tabular-nums text-gray-900">{fmt(line.amount)}</td>
        </tr>
      ))
    ) : (
      <tr className="border-b">
        <td className="py-2 pl-6 pr-4 text-gray-400 italic" colSpan={3}>
          {emptyText}
        </td>
      </tr>
    );

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b px-6 py-4">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900">Profit &amp; Loss</h1>
            <p className="text-xs text-gray-400 mt-0.5">
              {activeOrg?.org.name} · Cash basis
            </p>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={handleDownload}
              disabled={downloading || !hasData}
              className="bg-emerald-600 text-white px-4 py-2 rounded-lg hover:bg-emerald-700 text-sm font-medium disabled:opacity-50 transition"
            >
              {downloading ? "Preparing..." : "Export PDF"}
            </button>
            <button
              onClick={() => router.push("/dashboard")}
              className="text-gray-500 hover:text-gray-700 text-sm transition"
            >
              Back to dashboard
            </button>
          </div>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-6 py-6">
        {/* Period picker */}
        <div className="bg-white border rounded-xl p-4 mb-4">
          <p className="text-xs font-semibold text-gray-500 uppercase mb-3">Period</p>
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label className="text-xs text-gray-500 block mb-1">Year</label>
              <select
                value={year ?? ""}
                disabled={useCustom}
                onChange={(e) => setYear(Number(e.target.value))}
                className="border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100 disabled:text-gray-400"
              >
                {years.map((y) => (
                  <option key={y} value={y}>
                    {y}
                  </option>
                ))}
              </select>
            </div>

            <label className="flex items-center gap-2 text-sm text-gray-600 pb-1.5">
              <input
                type="checkbox"
                checked={useCustom}
                onChange={(e) => setUseCustom(e.target.checked)}
                className="rounded"
              />
              Custom range
            </label>

            {useCustom && (
              <>
                <div>
                  <label className="text-xs text-gray-500 block mb-1">Start Date</label>
                  <input
                    type="date"
                    value={startDate}
                    onChange={(e) => setStartDate(e.target.value)}
                    className="border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <div>
                  <label className="text-xs text-gray-500 block mb-1">End Date</label>
                  <input
                    type="date"
                    value={endDate}
                    onChange={(e) => setEndDate(e.target.value)}
                    className="border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <button
                  onClick={load}
                  className="bg-blue-600 text-white px-4 py-1.5 rounded-lg text-sm hover:bg-blue-700 transition"
                >
                  Apply
                </button>
              </>
            )}
          </div>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl px-4 py-3 mb-4">
            {error}
          </div>
        )}

        {loading ? (
          <div className="flex justify-center py-16">
            <div className="animate-pulse text-gray-400">Building statement...</div>
          </div>
        ) : !hasData ? (
          <div className="bg-white border rounded-xl py-16 text-center">
            <p className="text-gray-500">No transactions in this period</p>
            <p className="text-sm text-gray-400 mt-1">
              Upload statements or sync a bank account to build a P&amp;L.
            </p>
          </div>
        ) : (
          pnl && (
            <>
              {/* Headline cards */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-4">
                <div className="bg-emerald-50 border border-emerald-100 rounded-xl p-4">
                  <p className="text-xs font-semibold text-emerald-700 uppercase">Total Revenue</p>
                  <p className="text-2xl font-bold text-emerald-800 mt-1 tabular-nums">
                    {fmt(pnl.total_revenue)}
                  </p>
                </div>
                <div className="bg-red-50 border border-red-100 rounded-xl p-4">
                  <p className="text-xs font-semibold text-red-700 uppercase">Total Expenses</p>
                  <p className="text-2xl font-bold text-red-800 mt-1 tabular-nums">
                    {fmt(pnl.total_expenses)}
                  </p>
                </div>
                <div
                  className={`border rounded-xl p-4 ${
                    pnl.net_profit >= 0
                      ? "bg-blue-50 border-blue-100"
                      : "bg-orange-50 border-orange-100"
                  }`}
                >
                  <p
                    className={`text-xs font-semibold uppercase ${
                      pnl.net_profit >= 0 ? "text-blue-700" : "text-orange-700"
                    }`}
                  >
                    {pnl.net_profit >= 0 ? "Net Profit" : "Net Loss"}
                  </p>
                  <p
                    className={`text-2xl font-bold mt-1 tabular-nums ${
                      pnl.net_profit >= 0 ? "text-blue-800" : "text-orange-800"
                    }`}
                  >
                    {fmtAcct(pnl.net_profit)}
                  </p>
                  <p className="text-xs text-gray-500 mt-0.5">
                    {pnl.total_revenue ? `${pnl.margin_pct}% margin` : "no revenue"}
                  </p>
                </div>
              </div>

              {/* Statement */}
              <div className="bg-white border rounded-xl overflow-hidden mb-4">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-gray-900 text-white">
                      <th className="text-left py-2.5 px-4 font-semibold">Line item</th>
                      <th className="text-right py-2.5 pr-4 font-semibold w-20">Txns</th>
                      <th className="text-right py-2.5 pr-4 font-semibold w-40">Amount</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr className="bg-gray-100">
                      <td className="py-2 px-4 font-semibold text-gray-700 text-xs uppercase" colSpan={3}>
                        Revenue
                      </td>
                    </tr>
                    {renderLines(pnl.revenue_lines, "No revenue recorded in this period")}
                    <tr className="border-t-2 border-gray-300 font-semibold">
                      <td className="py-2 px-4 text-gray-900">Total Revenue</td>
                      <td />
                      <td className="py-2 pr-4 text-right tabular-nums text-gray-900">
                        {fmt(pnl.total_revenue)}
                      </td>
                    </tr>

                    <tr className="bg-gray-100">
                      <td className="py-2 px-4 font-semibold text-gray-700 text-xs uppercase" colSpan={3}>
                        Operating Expenses
                      </td>
                    </tr>
                    {renderLines(pnl.expense_lines, "No expenses recorded in this period")}
                    <tr className="border-t-2 border-gray-300 font-semibold">
                      <td className="py-2 px-4 text-gray-900">Total Operating Expenses</td>
                      <td />
                      <td className="py-2 pr-4 text-right tabular-nums text-gray-900">
                        {fmt(pnl.total_expenses)}
                      </td>
                    </tr>

                    <tr className="bg-gray-900 text-white font-bold">
                      <td className="py-3 px-4">
                        {pnl.net_profit >= 0 ? "NET PROFIT" : "NET LOSS"}
                      </td>
                      <td />
                      <td className="py-3 pr-4 text-right tabular-nums text-base">
                        {fmtAcct(pnl.net_profit)}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>

              {/* Excluded */}
              {pnl.excluded_lines.length > 0 && (
                <div className="bg-white border rounded-xl p-4 mb-4">
                  <p className="text-xs font-semibold text-gray-500 uppercase mb-2">
                    Excluded from P&amp;L
                  </p>
                  <table className="w-full text-sm mb-2">
                    <tbody>
                      {pnl.excluded_lines.map((line) => (
                        <tr key={line.label} className="border-b last:border-0">
                          <td className="py-1.5 text-gray-700">{line.label}</td>
                          <td className="py-1.5 text-right tabular-nums text-gray-900">
                            {fmt(line.amount)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <p className="text-xs text-gray-500 leading-relaxed">
                    These are balance-sheet movements, not income or expense, so they sit outside the
                    statement. Transfers are money between the owners&apos; own accounts — booking a
                    partner topping up the account as revenue would overstate income. Loan payments
                    are principal; the interest portion is a genuine expense, but bank transaction
                    data cannot separate it — ask your accountant to book that adjustment.
                  </p>
                </div>
              )}

              {/* Monthly breakdown */}
              {pnl.months.length > 1 && (
                <div className="bg-white border rounded-xl overflow-hidden">
                  <p className="text-xs font-semibold text-gray-500 uppercase px-4 pt-4 pb-2">
                    Monthly breakdown
                  </p>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs whitespace-nowrap">
                      <thead>
                        <tr className="bg-gray-900 text-white">
                          <th className="text-left py-2 px-4 font-semibold sticky left-0 bg-gray-900">
                            Month
                          </th>
                          <th className="text-right py-2 px-4 font-semibold">Revenue</th>
                          <th className="text-right py-2 px-4 font-semibold">Expenses</th>
                          <th className="text-right py-2 px-4 font-semibold">Net</th>
                        </tr>
                      </thead>
                      <tbody>
                        {pnl.monthly_summary.map((m) => (
                          <tr key={m.month} className="border-b last:border-0">
                            <td className="py-2 px-4 text-gray-700 sticky left-0 bg-white">
                              {monthLabel(m.month, multiYear)}
                            </td>
                            <td className="py-2 px-4 text-right tabular-nums text-gray-700">
                              {fmt(m.revenue)}
                            </td>
                            <td className="py-2 px-4 text-right tabular-nums text-gray-700">
                              {fmt(m.expenses)}
                            </td>
                            <td
                              className={`py-2 px-4 text-right tabular-nums font-medium ${
                                m.net >= 0 ? "text-emerald-700" : "text-red-700"
                              }`}
                            >
                              {fmtAcct(m.net)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              <p className="text-xs text-gray-400 mt-4">
                Cash basis — recognized when funds moved, not when invoiced.{" "}
                {pnl.transaction_count} transactions in period.
              </p>
            </>
          )
        )}
      </div>
    </div>
  );
}
