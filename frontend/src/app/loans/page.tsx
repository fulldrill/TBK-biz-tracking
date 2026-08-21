"use client";
import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { loanApi, transactionApi } from "@/lib/api";
import { Loan, LoanRepayment, Transaction } from "@/types";
import { useOrg } from "@/context/OrgContext";

const fmt = (val: number) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(val);

const STATUS_COLORS: Record<string, string> = {
  active: "bg-amber-100 text-amber-700",
  paid_off: "bg-emerald-100 text-emerald-700",
  written_off: "bg-gray-100 text-gray-500",
};

const STATUS_LABELS: Record<string, string> = {
  active: "Active",
  paid_off: "Paid Off",
  written_off: "Written Off",
};

export default function LoansPage() {
  const router = useRouter();
  const { activeOrg, isAdmin, isLoading: orgLoading } = useOrg();
  const orgId = activeOrg?.org.id;

  const [loans, setLoans] = useState<Loan[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedLoan, setSelectedLoan] = useState<Loan | null>(null);

  // New loan form
  const [showNewLoan, setShowNewLoan] = useState(false);
  const [newBorrower, setNewBorrower] = useState("");
  const [newPrincipal, setNewPrincipal] = useState("");
  const [newDateIssued, setNewDateIssued] = useState(new Date().toISOString().slice(0, 10));
  const [newNotes, setNewNotes] = useState("");
  const [saving, setSaving] = useState(false);

  // Repayment form
  const [showRepayment, setShowRepayment] = useState(false);
  const [repayAmount, setRepayAmount] = useState("");
  const [repayDate, setRepayDate] = useState(new Date().toISOString().slice(0, 10));
  const [repayNotes, setRepayNotes] = useState("");
  const [repayTxId, setRepayTxId] = useState("");
  const [addingRepayment, setAddingRepayment] = useState(false);

  // Edit loan
  const [editing, setEditing] = useState(false);
  const [editBorrower, setEditBorrower] = useState("");
  const [editPrincipal, setEditPrincipal] = useState("");
  const [editNotes, setEditNotes] = useState("");
  const [editStatus, setEditStatus] = useState("");

  const loadLoans = useCallback(async () => {
    if (!orgId) return;
    setLoading(true);
    try {
      const res = await loanApi.list(orgId);
      setLoans(res.data);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, [orgId]);

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
    loadLoans();
    // Load credit transactions for linking to repayments
    transactionApi
      .list(orgId!, { limit: 300, transaction_type: "credit" })
      .then((res) => setTransactions(res.data))
      .catch(() => {});
  }, [loadLoans, router, activeOrg, orgLoading, orgId]);

  const handleCreateLoan = async () => {
    if (!orgId || !newBorrower || !newPrincipal) return;
    setSaving(true);
    try {
      await loanApi.create(orgId, {
        borrower_name: newBorrower,
        principal: parseFloat(newPrincipal),
        date_issued: new Date(newDateIssued).toISOString(),
        notes: newNotes || undefined,
      });
      setShowNewLoan(false);
      setNewBorrower("");
      setNewPrincipal("");
      setNewNotes("");
      await loadLoans();
    } catch {
      alert("Failed to create loan.");
    } finally {
      setSaving(false);
    }
  };

  const handleAddRepayment = async () => {
    if (!orgId || !selectedLoan || !repayAmount) return;
    setAddingRepayment(true);
    try {
      await loanApi.addRepayment(orgId, selectedLoan.id, {
        amount: parseFloat(repayAmount),
        date: new Date(repayDate).toISOString(),
        notes: repayNotes || undefined,
        transaction_id: repayTxId || null,
      });
      setShowRepayment(false);
      setRepayAmount("");
      setRepayNotes("");
      setRepayTxId("");
      const res = await loanApi.get(orgId, selectedLoan.id);
      setSelectedLoan(res.data);
      await loadLoans();
    } catch {
      alert("Failed to add repayment.");
    } finally {
      setAddingRepayment(false);
    }
  };

  const handleDeleteRepayment = async (repayment: LoanRepayment) => {
    if (!orgId || !selectedLoan) return;
    if (!confirm("Remove this repayment?")) return;
    try {
      await loanApi.deleteRepayment(orgId, selectedLoan.id, repayment.id);
      const res = await loanApi.get(orgId, selectedLoan.id);
      setSelectedLoan(res.data);
      await loadLoans();
    } catch {
      alert("Failed to delete repayment.");
    }
  };

  const handleSaveEdit = async () => {
    if (!orgId || !selectedLoan) return;
    setSaving(true);
    try {
      const res = await loanApi.update(orgId, selectedLoan.id, {
        borrower_name: editBorrower,
        principal: parseFloat(editPrincipal),
        notes: editNotes || null,
        status: editStatus,
      });
      setSelectedLoan(res.data);
      setEditing(false);
      await loadLoans();
    } catch {
      alert("Failed to update loan.");
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteLoan = async (loan: Loan) => {
    if (!orgId) return;
    if (!confirm(`Delete loan for ${loan.borrower_name}? This cannot be undone.`)) return;
    try {
      await loanApi.delete(orgId, loan.id);
      if (selectedLoan?.id === loan.id) setSelectedLoan(null);
      await loadLoans();
    } catch {
      alert("Failed to delete loan.");
    }
  };

  const openLoan = (loan: Loan) => {
    setSelectedLoan(loan);
    setEditing(false);
    setShowRepayment(false);
    setEditBorrower(loan.borrower_name);
    setEditPrincipal(String(loan.principal));
    setEditNotes(loan.notes || "");
    setEditStatus(loan.status);
  };

  if (orgLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-pulse text-gray-400">Loading...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900">Loan Tracker</h1>
            <p className="text-xs text-gray-400 mt-0.5">Track money lent out and repayments</p>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => router.push("/dashboard")}
              className="text-gray-500 hover:text-gray-700 text-sm transition"
            >
              ← Dashboard
            </button>
            {isAdmin && (
              <button
                onClick={() => setShowNewLoan(true)}
                className="bg-indigo-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-indigo-700 transition"
              >
                + New Loan
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-6 flex gap-6">
        {/* Loan list */}
        <div className="w-80 shrink-0">
          {loading ? (
            <div className="animate-pulse text-gray-400 text-sm py-8 text-center">Loading...</div>
          ) : loans.length === 0 ? (
            <div className="text-center py-16 text-gray-400 border-2 border-dashed rounded-xl">
              <p>No loans yet</p>
              {isAdmin && (
                <button
                  onClick={() => setShowNewLoan(true)}
                  className="mt-2 text-sm text-indigo-600 hover:underline"
                >
                  Add your first loan
                </button>
              )}
            </div>
          ) : (
            <div className="space-y-2">
              {loans.map((loan) => (
                <div
                  key={loan.id}
                  onClick={() => openLoan(loan)}
                  className={`bg-white border rounded-xl p-4 cursor-pointer hover:border-indigo-300 transition ${
                    selectedLoan?.id === loan.id ? "border-indigo-400 ring-1 ring-indigo-200" : ""
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <p className="font-semibold text-gray-900 text-sm">{loan.borrower_name}</p>
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_COLORS[loan.status]}`}>
                      {STATUS_LABELS[loan.status]}
                    </span>
                  </div>
                  <p className="text-xs text-gray-500">Principal: {fmt(loan.principal)}</p>
                  <p className={`text-xs font-semibold mt-0.5 ${loan.outstanding_balance > 0 ? "text-red-500" : "text-emerald-600"}`}>
                    Outstanding: {fmt(loan.outstanding_balance)}
                  </p>
                  <p className="text-xs text-gray-400 mt-1">{new Date(loan.date_issued).toLocaleDateString()}</p>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Loan detail panel */}
        {selectedLoan && (
          <div className="flex-1 bg-white border rounded-xl p-6">
            {editing ? (
              <div className="space-y-4">
                <h2 className="text-lg font-semibold text-gray-900">Edit Loan</h2>
                <div>
                  <label className="text-xs text-gray-500 block mb-1">Borrower</label>
                  <input
                    value={editBorrower}
                    onChange={(e) => setEditBorrower(e.target.value)}
                    className="border rounded-lg px-3 py-2 text-sm w-full focus:outline-none focus:ring-2 focus:ring-indigo-400"
                  />
                </div>
                <div>
                  <label className="text-xs text-gray-500 block mb-1">Principal ($)</label>
                  <input
                    type="number"
                    value={editPrincipal}
                    onChange={(e) => setEditPrincipal(e.target.value)}
                    className="border rounded-lg px-3 py-2 text-sm w-full focus:outline-none focus:ring-2 focus:ring-indigo-400"
                  />
                </div>
                <div>
                  <label className="text-xs text-gray-500 block mb-1">Status</label>
                  <select
                    value={editStatus}
                    onChange={(e) => setEditStatus(e.target.value)}
                    className="border rounded-lg px-3 py-2 text-sm w-full focus:outline-none focus:ring-2 focus:ring-indigo-400"
                  >
                    <option value="active">Active</option>
                    <option value="paid_off">Paid Off</option>
                    <option value="written_off">Written Off</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs text-gray-500 block mb-1">Notes</label>
                  <textarea
                    value={editNotes}
                    onChange={(e) => setEditNotes(e.target.value)}
                    rows={3}
                    className="border rounded-lg px-3 py-2 text-sm w-full focus:outline-none focus:ring-2 focus:ring-indigo-400"
                  />
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={handleSaveEdit}
                    disabled={saving}
                    className="bg-indigo-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
                  >
                    {saving ? "Saving..." : "Save"}
                  </button>
                  <button
                    onClick={() => setEditing(false)}
                    className="text-gray-500 hover:text-gray-700 text-sm px-4 py-2"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <>
                <div className="flex items-start justify-between mb-6">
                  <div>
                    <h2 className="text-xl font-bold text-gray-900">{selectedLoan.borrower_name}</h2>
                    <p className="text-xs text-gray-400 mt-0.5">
                      Issued {new Date(selectedLoan.date_issued).toLocaleDateString()}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`text-xs px-2 py-1 rounded-full font-medium ${STATUS_COLORS[selectedLoan.status]}`}>
                      {STATUS_LABELS[selectedLoan.status]}
                    </span>
                    {isAdmin && (
                      <>
                        <button
                          onClick={() => setEditing(true)}
                          className="text-gray-400 hover:text-gray-700 text-xs border rounded-lg px-3 py-1 transition"
                        >
                          Edit
                        </button>
                        <button
                          onClick={() => handleDeleteLoan(selectedLoan)}
                          className="text-red-400 hover:text-red-600 text-xs border border-red-200 rounded-lg px-3 py-1 transition"
                        >
                          Delete
                        </button>
                      </>
                    )}
                  </div>
                </div>

                {/* Amounts */}
                <div className="grid grid-cols-3 gap-4 mb-6">
                  <div className="bg-gray-50 rounded-xl p-3">
                    <p className="text-xs text-gray-400">Principal</p>
                    <p className="text-lg font-semibold text-gray-800">{fmt(selectedLoan.principal)}</p>
                  </div>
                  <div className="bg-emerald-50 rounded-xl p-3">
                    <p className="text-xs text-gray-400">Total Repaid</p>
                    <p className="text-lg font-semibold text-emerald-600">
                      {fmt(selectedLoan.repayments.reduce((s, r) => s + r.amount, 0))}
                    </p>
                  </div>
                  <div className={`rounded-xl p-3 ${selectedLoan.outstanding_balance > 0 ? "bg-red-50" : "bg-gray-50"}`}>
                    <p className="text-xs text-gray-400">Outstanding</p>
                    <p className={`text-lg font-semibold ${selectedLoan.outstanding_balance > 0 ? "text-red-500" : "text-gray-400"}`}>
                      {fmt(selectedLoan.outstanding_balance)}
                    </p>
                  </div>
                </div>

                {selectedLoan.notes && (
                  <p className="text-sm text-gray-500 mb-6 bg-gray-50 rounded-xl px-4 py-3">{selectedLoan.notes}</p>
                )}

                {/* Repayments */}
                <div className="flex items-center justify-between mb-3">
                  <p className="text-xs font-semibold text-gray-500 uppercase">Repayments</p>
                  {isAdmin && (
                    <button
                      onClick={() => setShowRepayment(!showRepayment)}
                      className="text-xs text-indigo-600 hover:underline font-medium"
                    >
                      + Add Repayment
                    </button>
                  )}
                </div>

                {showRepayment && (
                  <div className="bg-indigo-50 border border-indigo-200 rounded-xl p-4 mb-4 space-y-3">
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="text-xs text-gray-500 block mb-1">Amount ($)</label>
                        <input
                          type="number"
                          value={repayAmount}
                          onChange={(e) => setRepayAmount(e.target.value)}
                          className="border rounded-lg px-3 py-1.5 text-sm w-full focus:outline-none focus:ring-2 focus:ring-indigo-400"
                          placeholder="0.00"
                        />
                      </div>
                      <div>
                        <label className="text-xs text-gray-500 block mb-1">Date</label>
                        <input
                          type="date"
                          value={repayDate}
                          onChange={(e) => setRepayDate(e.target.value)}
                          className="border rounded-lg px-3 py-1.5 text-sm w-full focus:outline-none focus:ring-2 focus:ring-indigo-400"
                        />
                      </div>
                    </div>
                    <div>
                      <label className="text-xs text-gray-500 block mb-1">Link to Transaction (optional)</label>
                      <select
                        value={repayTxId}
                        onChange={(e) => setRepayTxId(e.target.value)}
                        className="border rounded-lg px-3 py-1.5 text-sm w-full focus:outline-none focus:ring-2 focus:ring-indigo-400"
                      >
                        <option value="">— No linked transaction —</option>
                        {transactions.map((tx) => (
                          <option key={tx.id} value={tx.id}>
                            {tx.date?.slice(0, 10)} | {tx.name} | {fmt(tx.amount)}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="text-xs text-gray-500 block mb-1">Notes</label>
                      <input
                        value={repayNotes}
                        onChange={(e) => setRepayNotes(e.target.value)}
                        className="border rounded-lg px-3 py-1.5 text-sm w-full focus:outline-none focus:ring-2 focus:ring-indigo-400"
                        placeholder="Optional note..."
                      />
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={handleAddRepayment}
                        disabled={addingRepayment || !repayAmount}
                        className="bg-indigo-600 text-white px-4 py-1.5 rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
                      >
                        {addingRepayment ? "Adding..." : "Add Repayment"}
                      </button>
                      <button
                        onClick={() => setShowRepayment(false)}
                        className="text-gray-500 text-sm px-3 py-1.5"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}

                {selectedLoan.repayments.length === 0 ? (
                  <p className="text-sm text-gray-400 py-4 text-center">No repayments recorded yet.</p>
                ) : (
                  <div className="space-y-2">
                    {[...selectedLoan.repayments]
                      .sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())
                      .map((r) => {
                        const linkedTx = r.transaction_id
                          ? transactions.find((t) => t.id === r.transaction_id)
                          : null;
                        return (
                          <div
                            key={r.id}
                            className="flex items-center justify-between bg-gray-50 rounded-xl px-4 py-3"
                          >
                            <div>
                              <p className="text-sm font-semibold text-emerald-600">{fmt(r.amount)}</p>
                              <p className="text-xs text-gray-400">{new Date(r.date).toLocaleDateString()}</p>
                              {r.notes && <p className="text-xs text-gray-500 mt-0.5">{r.notes}</p>}
                              {linkedTx && (
                                <p className="text-xs text-indigo-500 mt-0.5">
                                  Linked: {linkedTx.name?.slice(0, 40)}
                                </p>
                              )}
                            </div>
                            {isAdmin && (
                              <button
                                onClick={() => handleDeleteRepayment(r)}
                                className="text-red-400 hover:text-red-600 text-xs ml-4"
                              >
                                Remove
                              </button>
                            )}
                          </div>
                        );
                      })}
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {!selectedLoan && !loading && loans.length > 0 && (
          <div className="flex-1 flex items-center justify-center text-gray-400">
            <p>Select a loan to view details</p>
          </div>
        )}
      </div>

      {/* New Loan Modal */}
      {showNewLoan && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl shadow-xl p-6 w-full max-w-md">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">New Loan</h2>
            <div className="space-y-3">
              <div>
                <label className="text-xs text-gray-500 block mb-1">Borrower Name</label>
                <input
                  value={newBorrower}
                  onChange={(e) => setNewBorrower(e.target.value)}
                  className="border rounded-lg px-3 py-2 text-sm w-full focus:outline-none focus:ring-2 focus:ring-indigo-400"
                  placeholder="e.g. John Smith"
                />
              </div>
              <div>
                <label className="text-xs text-gray-500 block mb-1">Principal Amount ($)</label>
                <input
                  type="number"
                  value={newPrincipal}
                  onChange={(e) => setNewPrincipal(e.target.value)}
                  className="border rounded-lg px-3 py-2 text-sm w-full focus:outline-none focus:ring-2 focus:ring-indigo-400"
                  placeholder="0.00"
                />
              </div>
              <div>
                <label className="text-xs text-gray-500 block mb-1">Date Issued</label>
                <input
                  type="date"
                  value={newDateIssued}
                  onChange={(e) => setNewDateIssued(e.target.value)}
                  className="border rounded-lg px-3 py-2 text-sm w-full focus:outline-none focus:ring-2 focus:ring-indigo-400"
                />
              </div>
              <div>
                <label className="text-xs text-gray-500 block mb-1">Notes (optional)</label>
                <textarea
                  value={newNotes}
                  onChange={(e) => setNewNotes(e.target.value)}
                  rows={2}
                  className="border rounded-lg px-3 py-2 text-sm w-full focus:outline-none focus:ring-2 focus:ring-indigo-400"
                  placeholder="Purpose, terms, etc."
                />
              </div>
            </div>
            <div className="flex gap-2 mt-5">
              <button
                onClick={handleCreateLoan}
                disabled={saving || !newBorrower || !newPrincipal}
                className="flex-1 bg-indigo-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
              >
                {saving ? "Creating..." : "Create Loan"}
              </button>
              <button
                onClick={() => setShowNewLoan(false)}
                className="flex-1 border py-2 rounded-lg text-sm text-gray-600 hover:bg-gray-50"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
