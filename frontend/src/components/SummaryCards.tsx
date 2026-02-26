"use client";
import { Totals } from "@/types";

interface Props {
  totals: Totals;
}

const fmt = (val: number) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(val);

export default function SummaryCards({ totals }: Props) {
  const cards = [
    {
      label: "Total Deposits",
      value: totals.total_deposits,
      color: "bg-emerald-50 border-emerald-200",
      text: "text-emerald-700",
      icon: "↑",
    },
    {
      label: "Total Withdrawals",
      value: totals.total_withdrawals,
      color: "bg-red-50 border-red-200",
      text: "text-red-700",
      icon: "↓",
    },
    {
      label: "Zelle Sent",
      value: totals.zelle_sent,
      color: "bg-orange-50 border-orange-200",
      text: "text-orange-700",
      icon: "Z↑",
    },
    {
      label: "Zelle Received",
      value: totals.zelle_received,
      color: "bg-purple-50 border-purple-200",
      text: "text-purple-700",
      icon: "Z↓",
    },
    {
      label: "Net Balance",
      value: totals.net_balance,
      color: totals.net_balance >= 0 ? "bg-blue-50 border-blue-200" : "bg-red-50 border-red-200",
      text: totals.net_balance >= 0 ? "text-blue-700" : "text-red-700",
      icon: "=",
    },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
      {cards.map((card) => (
        <div key={card.label} className={`border rounded-xl p-4 ${card.color}`}>
          <div className="flex items-center justify-between mb-1">
            <p className={`text-xs font-medium uppercase tracking-wide opacity-60 ${card.text}`}>
              {card.label}
            </p>
            <span className={`text-lg font-bold opacity-40 ${card.text}`}>{card.icon}</span>
          </div>
          <p className={`text-xl font-bold ${card.text}`}>{fmt(card.value)}</p>
        </div>
      ))}
    </div>
  );
}
