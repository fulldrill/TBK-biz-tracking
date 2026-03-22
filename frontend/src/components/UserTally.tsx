"use client";
import { Transaction } from "@/types";

interface Props {
  transactions: Transaction[];
}

const fmt = (val: number) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(val);

interface UserStats {
  deposits: number;
  withdrawals: number;
  zelleIn: number;
  zelleOut: number;
  count: number;
}

function calcStats(txns: Transaction[]): UserStats {
  return txns.reduce(
    (acc, tx) => {
      if (tx.transaction_type === "credit") {
        acc.deposits += tx.amount;
        if (tx.is_zelle) acc.zelleIn += tx.amount;
      } else {
        acc.withdrawals += tx.amount;
        if (tx.is_zelle) acc.zelleOut += tx.amount;
      }
      acc.count += 1;
      return acc;
    },
    { deposits: 0, withdrawals: 0, zelleIn: 0, zelleOut: 0, count: 0 }
  );
}

const USERS = [
  {
    name: "Kenny",
    avatar: "K",
    border: "border-blue-200",
    bg: "bg-blue-50",
    avatarBg: "bg-blue-600",
    label: "text-blue-700",
    role: "Debit card & POS purchases",
  },
  {
    name: "Bright",
    avatar: "B",
    border: "border-amber-200",
    bg: "bg-amber-50",
    avatarBg: "bg-amber-500",
    label: "text-amber-700",
    role: "Zelle & walk-in deposits",
  },
  {
    name: "Tony",
    avatar: "T",
    border: "border-teal-200",
    bg: "bg-teal-50",
    avatarBg: "bg-teal-600",
    label: "text-teal-700",
    role: "Deposits (manual assignment)",
  },
];

export default function UserTally({ transactions }: Props) {
  const byUser: Record<string, Transaction[]> = { Kenny: [], Bright: [], Tony: [], Unassigned: [] };

  for (const tx of transactions) {
    const u = tx.assigned_user;
    if (u === "Kenny") byUser.Kenny.push(tx);
    else if (u === "Bright") byUser.Bright.push(tx);
    else if (u === "Tony") byUser.Tony.push(tx);
    else byUser.Unassigned.push(tx);
  }

  if (transactions.length === 0) return null;

  return (
    <div className="mb-6">
      <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">
        Per-User Totals
      </p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {USERS.map(({ name, avatar, border, bg, avatarBg, label, role }) => {
          const stats = calcStats(byUser[name]);
          const net = stats.deposits - stats.withdrawals;

          return (
            <div key={name} className={`border ${border} ${bg} rounded-xl p-5`}>
              {/* Header */}
              <div className="flex items-center gap-3 mb-4">
                <div className={`w-9 h-9 rounded-full ${avatarBg} flex items-center justify-center text-white font-bold text-sm`}>
                  {avatar}
                </div>
                <div>
                  <p className={`font-semibold text-sm ${label}`}>{name}</p>
                  <p className="text-xs text-gray-400">{role} · {stats.count} txns</p>
                </div>
                {/* Net badge */}
                <div className={`ml-auto text-sm font-bold ${net >= 0 ? "text-emerald-600" : "text-red-600"}`}>
                  {net >= 0 ? "+" : ""}{fmt(net)}
                  <p className="text-xs font-normal text-gray-400 text-right">net</p>
                </div>
              </div>

              {/* Stats grid */}
              <div className="grid grid-cols-2 gap-3">
                <div className="bg-white/60 rounded-lg px-3 py-2.5">
                  <p className="text-xs text-gray-400 mb-0.5">Deposits</p>
                  <p className="text-base font-bold text-emerald-600">+{fmt(stats.deposits)}</p>
                </div>
                <div className="bg-white/60 rounded-lg px-3 py-2.5">
                  <p className="text-xs text-gray-400 mb-0.5">Withdrawals</p>
                  <p className="text-base font-bold text-red-600">−{fmt(stats.withdrawals)}</p>
                </div>
                {stats.zelleIn > 0 && (
                  <div className="bg-white/60 rounded-lg px-3 py-2.5">
                    <p className="text-xs text-gray-400 mb-0.5">Zelle In</p>
                    <p className="text-base font-bold text-purple-600">+{fmt(stats.zelleIn)}</p>
                  </div>
                )}
                {stats.zelleOut > 0 && (
                  <div className="bg-white/60 rounded-lg px-3 py-2.5">
                    <p className="text-xs text-gray-400 mb-0.5">Zelle Out</p>
                    <p className="text-base font-bold text-orange-600">−{fmt(stats.zelleOut)}</p>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Unassigned row — only shown if any exist */}
      {byUser.Unassigned.length > 0 && (() => {
        const stats = calcStats(byUser.Unassigned);
        const net = stats.deposits - stats.withdrawals;
        return (
          <div className="mt-3 border border-gray-200 bg-gray-50 rounded-xl px-5 py-3 flex items-center gap-4 flex-wrap">
            <div className="w-7 h-7 rounded-full bg-gray-300 flex items-center justify-center text-gray-600 font-bold text-xs">?</div>
            <div>
              <p className="text-sm font-medium text-gray-600">Unassigned</p>
              <p className="text-xs text-gray-400">{stats.count} transactions</p>
            </div>
            <div className="flex gap-4 ml-4 flex-wrap text-sm">
              <span className="text-emerald-600 font-semibold">+{fmt(stats.deposits)}</span>
              <span className="text-red-600 font-semibold">−{fmt(stats.withdrawals)}</span>
              <span className={`font-semibold ${net >= 0 ? "text-emerald-600" : "text-red-600"}`}>
                Net {net >= 0 ? "+" : ""}{fmt(net)}
              </span>
            </div>
          </div>
        );
      })()}
    </div>
  );
}
