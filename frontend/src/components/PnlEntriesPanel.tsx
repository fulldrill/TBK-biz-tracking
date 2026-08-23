"use client";
import { useState, useEffect, useCallback } from "react";
import { reportApi, getErrorMessage } from "@/lib/api";
import { PnlEntry, PnlEntryType, PnlRecurrence } from "@/types";

const fmt = (val: number) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(val);

/** Negatives in parentheses, matching the statement. */
const fmtAcct = (val: number) => (val < 0 ? `(${fmt(Math.abs(val))})` : fmt(val));

interface Props {
  orgId: string;
  isAdmin: boolean;
  /** Called after any change so the parent can rebuild the statement. */
  onChanged: () => void;
}

/**
 * Manual P&L lines — real costs and income that never touched the bank
 * account, such as the home-office rent the business owes.
 */
export default function PnlEntriesPanel({ orgId, isAdmin, onChanged }: Props) {
  const [entries, setEntries] = useState<PnlEntry[]>([]);
  const [open, setOpen] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const [label, setLabel] = useState("");
  const [amount, setAmount] = useState("");
  const [entryType, setEntryType] = useState<PnlEntryType>("expense");
  const [recurrence, setRecurrence] = useState<PnlRecurrence>("monthly");
  const [startDate, setStartDate] = useState(new Date().toISOString().slice(0, 10));
  const [endDate, setEndDate] = useState("");
  const [notes, setNotes] = useState("");

  const load = useCallback(async () => {
    if (!orgId) return;
    try {
      const res = await reportApi.listEntries(orgId);
      setEntries(res.data);
    } catch {
      /* non-fatal — the statement still renders without this panel */
    }
  }, [orgId]);

  useEffect(() => {
    load();
  }, [load]);

  const reset = () => {
    setLabel("");
    setAmount("");
    setEntryType("expense");
    setRecurrence("monthly");
    setStartDate(new Date().toISOString().slice(0, 10));
    setEndDate("");
    setNotes("");
    setError("");
  };

  const handleCreate = async () => {
    if (!label.trim() || !amount) {
      setError("Give the line a name and an amount.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await reportApi.createEntry(orgId, {
        label: label.trim(),
        amount: Number(amount),
        entry_type: entryType,
        recurrence,
        start_date: `${startDate}T00:00:00`,
        end_date: endDate ? `${endDate}T00:00:00` : null,
        notes: notes.trim() || null,
      });
      reset();
      setShowForm(false);
      await load();
      onChanged();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (entry: PnlEntry) => {
    if (!confirm(`Remove "${entry.label}" from the P&L?`)) return;
    try {
      await reportApi.deleteEntry(orgId, entry.id);
      await load();
      onChanged();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const handleToggle = async (entry: PnlEntry) => {
    try {
      await reportApi.updateEntry(orgId, entry.id, { is_active: !entry.is_active });
      await load();
      onChanged();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const activeCount = entries.filter((e) => e.is_active).length;

  return (
    <div className="bg-white border rounded-xl mb-4">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-4 py-3 text-left"
      >
        <span className="text-xs font-semibold text-gray-500 uppercase">
          Manual entries
          {activeCount > 0 && (
            <span className="ml-2 text-teal-600 normal-case font-medium">
              {activeCount} active
            </span>
          )}
        </span>
        <span className="text-gray-400 text-sm">{open ? "Hide" : "Show"}</span>
      </button>

      {open && (
        <div className="px-4 pb-4">
          <p className="text-xs text-gray-500 mb-3">
            Costs and income that never hit the bank account — the rent you owe for the
            basement office, cash sales, an adjustment your accountant asked for. These
            appear on the P&amp;L marked with an asterisk. Use a{" "}
            <strong>negative amount</strong> to subtract instead of add, for a refund or
            a correction.
          </p>

          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg px-3 py-2 mb-3">
              {error}
            </div>
          )}

          {entries.length > 0 && (
            <table className="w-full text-sm mb-3">
              <thead>
                <tr className="text-xs text-gray-500 uppercase border-b">
                  <th className="text-left py-1.5">Line</th>
                  <th className="text-left py-1.5">Type</th>
                  <th className="text-left py-1.5">Repeats</th>
                  <th className="text-left py-1.5">Period</th>
                  <th className="text-right py-1.5">Amount</th>
                  {isAdmin && <th className="w-24" />}
                </tr>
              </thead>
              <tbody>
                {entries.map((e) => (
                  <tr
                    key={e.id}
                    className={`border-b last:border-0 ${e.is_active ? "" : "opacity-40"}`}
                  >
                    <td className="py-2 text-gray-800">
                      {e.label}
                      {e.notes && (
                        <span className="block text-xs text-gray-400">{e.notes}</span>
                      )}
                    </td>
                    <td className="py-2">
                      <span
                        className={`text-xs px-2 py-0.5 rounded-full ${
                          e.entry_type === "revenue"
                            ? "bg-emerald-100 text-emerald-700"
                            : "bg-red-100 text-red-700"
                        }`}
                      >
                        {e.entry_type}
                      </span>
                    </td>
                    <td className="py-2 text-gray-600">
                      {e.recurrence === "monthly" ? "Monthly" : "One-off"}
                    </td>
                    <td className="py-2 text-gray-600 text-xs">
                      {e.start_date.slice(0, 10)}
                      {e.recurrence === "monthly" &&
                        ` → ${e.end_date ? e.end_date.slice(0, 10) : "ongoing"}`}
                    </td>
                    <td
                      className={`py-2 text-right tabular-nums ${
                        e.amount < 0 ? "text-blue-700" : "text-gray-900"
                      }`}
                    >
                      {fmtAcct(e.amount)}
                      {e.recurrence === "monthly" && (
                        <span className="text-xs text-gray-400">/mo</span>
                      )}
                    </td>
                    {isAdmin && (
                      <td className="py-2 text-right">
                        <button
                          onClick={() => handleToggle(e)}
                          className="text-xs text-gray-500 hover:text-gray-700 mr-2"
                        >
                          {e.is_active ? "Pause" : "Resume"}
                        </button>
                        <button
                          onClick={() => handleDelete(e)}
                          className="text-xs text-red-600 hover:text-red-700"
                        >
                          Delete
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {isAdmin && !showForm && (
            <button
              onClick={() => setShowForm(true)}
              className="bg-teal-600 text-white px-3 py-1.5 rounded-lg text-sm hover:bg-teal-700 transition"
            >
              Add entry
            </button>
          )}

          {isAdmin && showForm && (
            <div className="border rounded-lg p-3 bg-gray-50">
              <div className="flex flex-wrap gap-3 mb-3">
                <div className="flex-1 min-w-[180px]">
                  <label className="text-xs text-gray-500 block mb-1">Label</label>
                  <input
                    type="text"
                    placeholder="Basement Office Rent"
                    value={label}
                    onChange={(e) => setLabel(e.target.value)}
                    className="w-full border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
                  />
                </div>
                <div>
                  <label className="text-xs text-gray-500 block mb-1">Amount</label>
                  <input
                    type="number"
                    step="0.01"
                    placeholder="1600.00 (or -300 to subtract)"
                    value={amount}
                    onChange={(e) => setAmount(e.target.value)}
                    className="w-32 border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
                  />
                </div>
                <div>
                  <label className="text-xs text-gray-500 block mb-1">Type</label>
                  <select
                    value={entryType}
                    onChange={(e) => setEntryType(e.target.value as PnlEntryType)}
                    className="border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
                  >
                    <option value="expense">Expense</option>
                    <option value="revenue">Revenue</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs text-gray-500 block mb-1">Repeats</label>
                  <select
                    value={recurrence}
                    onChange={(e) => setRecurrence(e.target.value as PnlRecurrence)}
                    className="border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
                  >
                    <option value="monthly">Every month</option>
                    <option value="once">One-off</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs text-gray-500 block mb-1">
                    {recurrence === "monthly" ? "Starts" : "Date"}
                  </label>
                  <input
                    type="date"
                    value={startDate}
                    onChange={(e) => setStartDate(e.target.value)}
                    className="border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
                  />
                </div>
                {recurrence === "monthly" && (
                  <div>
                    <label className="text-xs text-gray-500 block mb-1">
                      Ends <span className="text-gray-400">(optional)</span>
                    </label>
                    <input
                      type="date"
                      value={endDate}
                      onChange={(e) => setEndDate(e.target.value)}
                      className="border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
                    />
                  </div>
                )}
                <div className="flex-1 min-w-[160px]">
                  <label className="text-xs text-gray-500 block mb-1">
                    Notes <span className="text-gray-400">(optional)</span>
                  </label>
                  <input
                    type="text"
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    className="w-full border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
                  />
                </div>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={handleCreate}
                  disabled={saving}
                  className="bg-teal-600 text-white px-4 py-1.5 rounded-lg text-sm hover:bg-teal-700 disabled:opacity-50 transition"
                >
                  {saving ? "Saving..." : "Save entry"}
                </button>
                <button
                  onClick={() => {
                    reset();
                    setShowForm(false);
                  }}
                  className="text-gray-500 hover:text-gray-700 px-3 py-1.5 text-sm"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
