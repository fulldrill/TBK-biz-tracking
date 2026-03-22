"use client";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useOrg } from "@/context/OrgContext";
import { orgApi } from "@/lib/api";
import { UserOrg } from "@/types";

export default function OrgsPage() {
  const router = useRouter();
  const { orgs, isLoading, setActiveOrg, refreshOrgs } = useOrg();
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
    if (!token) {
      router.push("/auth");
    }
  }, [router]);

  const selectOrg = (u: UserOrg) => {
    setActiveOrg(u);
    router.push("/dashboard");
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) return;
    setCreating(true);
    setError("");
    try {
      await orgApi.create(newName.trim());
      await refreshOrgs();
      setNewName("");
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(msg || "Failed to create organization.");
    } finally {
      setCreating(false);
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="animate-pulse text-gray-400">Loading...</div>
      </div>
    );
  }

  const roleBadge = (role: string) => (
    <span
      className={`text-xs px-2 py-0.5 rounded font-medium ${
        role === "admin" ? "bg-blue-100 text-blue-700" : "bg-gray-100 text-gray-500"
      }`}
    >
      {role}
    </span>
  );

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center p-6">
      <div className="w-full max-w-lg">
        <h1 className="text-2xl font-bold text-gray-900 mb-1">Your Organizations</h1>
        <p className="text-sm text-gray-500 mb-6">Select a business or create a new one.</p>

        {orgs.length === 0 && (
          <div className="text-center py-8 text-gray-400 border-2 border-dashed rounded-xl mb-6">
            No organizations yet. Create your first one below.
          </div>
        )}

        <div className="space-y-3 mb-8">
          {orgs.map((u) => (
            <button
              key={u.org.id}
              onClick={() => selectOrg(u)}
              className="w-full text-left bg-white border rounded-xl px-5 py-4 hover:shadow-md transition flex items-center justify-between group"
            >
              <div>
                <p className="font-medium text-gray-900">{u.org.name}</p>
                <p className="text-xs text-gray-400 mt-0.5">{u.member_count} member{u.member_count !== 1 ? "s" : ""}</p>
              </div>
              <div className="flex items-center gap-3">
                {roleBadge(u.role)}
                <svg className="w-4 h-4 text-gray-300 group-hover:text-gray-500 transition" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              </div>
            </button>
          ))}
        </div>

        <div className="bg-white border rounded-xl p-5">
          <h2 className="font-semibold text-gray-800 mb-3">Create New Organization</h2>
          <form onSubmit={handleCreate} className="flex gap-3">
            <input
              type="text"
              placeholder="Business name"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              className="flex-1 border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <button
              type="submit"
              disabled={creating || !newName.trim()}
              className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition"
            >
              {creating ? "Creating..." : "Create"}
            </button>
          </form>
          {error && <p className="text-red-500 text-xs mt-2">{error}</p>}
        </div>
      </div>
    </div>
  );
}
