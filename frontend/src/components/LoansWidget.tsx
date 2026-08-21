"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { loanApi } from "@/lib/api";
import { LoanSummary } from "@/types";

const fmt = (val: number) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(val);

export default function LoansWidget({ orgId }: { orgId: string }) {
  const router = useRouter();
  const [summary, setSummary] = useState<LoanSummary | null>(null);

  useEffect(() => {
    loanApi.summary(orgId).then((res) => setSummary(res.data)).catch(() => {});
  }, [orgId]);

  if (!summary) return null;

  return (
    <div
      className="bg-white border rounded-xl p-4 mb-4 cursor-pointer hover:border-indigo-300 transition"
      onClick={() => router.push("/loans")}
    >
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs font-semibold text-gray-500 uppercase">Loan Tracker</p>
        <span className="text-xs text-indigo-600 font-medium hover:underline">Manage →</span>
      </div>
      <div className="grid grid-cols-4 gap-3">
        <div>
          <p className="text-xs text-gray-400">Total Loaned</p>
          <p className="text-base font-semibold text-gray-800">{fmt(summary.total_loaned)}</p>
        </div>
        <div>
          <p className="text-xs text-gray-400">Total Repaid</p>
          <p className="text-base font-semibold text-emerald-600">{fmt(summary.total_repaid)}</p>
        </div>
        <div>
          <p className="text-xs text-gray-400">Outstanding</p>
          <p className={`text-base font-semibold ${summary.total_outstanding > 0 ? "text-red-500" : "text-gray-400"}`}>
            {fmt(summary.total_outstanding)}
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-400">Active Loans</p>
          <p className="text-base font-semibold text-gray-800">{summary.active_loan_count}</p>
        </div>
      </div>
    </div>
  );
}
