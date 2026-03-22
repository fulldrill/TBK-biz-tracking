"use client";
import { useEffect, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import { orgApi } from "@/lib/api";
import { OrgMember, OrgInvite } from "@/types";
import { useOrg } from "@/context/OrgContext";

type Tab = "general" | "members" | "invites" | "danger";

export default function OrgSettingsPage() {
  const params = useParams();
  const orgId = params.orgId as string;
  const router = useRouter();
  const { activeOrg, isAdmin, refreshOrgs, setActiveOrg, orgs } = useOrg();

  const [tab, setTab] = useState<Tab>("general");
  const [orgName, setOrgName] = useState(activeOrg?.org.name ?? "");
  const [savingName, setSavingName] = useState(false);

  const [members, setMembers] = useState<OrgMember[]>([]);
  const [invites, setInvites] = useState<OrgInvite[]>([]);
  const [loadingMembers, setLoadingMembers] = useState(false);
  const [loadingInvites, setLoadingInvites] = useState(false);

  const [newInviteRole, setNewInviteRole] = useState<"admin" | "viewer">("viewer");
  const [creatingInvite, setCreatingInvite] = useState(false);
  const [copiedToken, setCopiedToken] = useState<string | null>(null);

  const [appUrl, setAppUrl] = useState("");

  useEffect(() => {
    if (typeof window !== "undefined") {
      setAppUrl(`${window.location.protocol}//${window.location.host}`);
    }
  }, []);

  useEffect(() => {
    if (!isAdmin) return;
    setLoadingMembers(true);
    orgApi.getMembers(orgId).then((r) => {
      setMembers(r.data);
      setLoadingMembers(false);
    });
  }, [orgId, isAdmin]);

  useEffect(() => {
    if (!isAdmin || tab !== "invites") return;
    setLoadingInvites(true);
    orgApi.listInvites(orgId).then((r) => {
      setInvites(r.data);
      setLoadingInvites(false);
    });
  }, [orgId, isAdmin, tab]);

  const handleSaveName = async () => {
    setSavingName(true);
    try {
      await orgApi.update(orgId, orgName);
      await refreshOrgs();
    } finally {
      setSavingName(false);
    }
  };

  const handleRemoveMember = async (userId: string) => {
    if (!confirm("Remove this member?")) return;
    await orgApi.removeMember(orgId, userId);
    setMembers((m) => m.filter((x) => x.user_id !== userId));
  };

  const handleRoleChange = async (userId: string, role: string) => {
    await orgApi.updateMemberRole(orgId, userId, role);
    setMembers((m) => m.map((x) => (x.user_id === userId ? { ...x, role: role as "admin" | "viewer" } : x)));
  };

  const handleCreateInvite = async () => {
    setCreatingInvite(true);
    try {
      const r = await orgApi.createInvite(orgId, newInviteRole);
      setInvites((prev) => [...prev, r.data]);
    } finally {
      setCreatingInvite(false);
    }
  };

  const handleRevokeInvite = async (inviteId: string) => {
    await orgApi.revokeInvite(orgId, inviteId);
    setInvites((prev) => prev.filter((i) => i.id !== inviteId));
  };

  const copyInviteLink = (token: string) => {
    navigator.clipboard.writeText(`${appUrl}/invite/${token}`);
    setCopiedToken(token);
    setTimeout(() => setCopiedToken(null), 2000);
  };

  const handleDeleteOrg = async () => {
    if (!confirm("This will permanently delete the organization and all its data. Are you sure?")) return;
    try {
      await orgApi.delete(orgId);
      await refreshOrgs();
      const remaining = orgs.filter((u) => u.org.id !== orgId);
      if (remaining.length > 0) {
        setActiveOrg(remaining[0]);
        router.push("/dashboard");
      } else {
        router.push("/orgs");
      }
    } catch {
      alert("Failed to delete organization.");
    }
  };

  if (!isAdmin) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <p className="text-gray-500">Admin access required.</p>
      </div>
    );
  }

  const tabs: { id: Tab; label: string }[] = [
    { id: "general", label: "General" },
    { id: "members", label: "Members" },
    { id: "invites", label: "Invites" },
    { id: "danger", label: "Danger Zone" },
  ];

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-3xl mx-auto px-6 py-10">
        <div className="flex items-center gap-3 mb-8">
          <button onClick={() => router.push("/dashboard")} className="text-gray-400 hover:text-gray-600 text-sm">
            ← Dashboard
          </button>
          <h1 className="text-xl font-bold text-gray-900">Organization Settings</h1>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 mb-6 border-b">
          {tabs.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`px-4 py-2 text-sm font-medium transition border-b-2 -mb-px ${
                tab === t.id
                  ? "border-blue-600 text-blue-600"
                  : "border-transparent text-gray-500 hover:text-gray-700"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* General */}
        {tab === "general" && (
          <div className="bg-white border rounded-xl p-6">
            <h2 className="font-semibold text-gray-800 mb-4">Organization Name</h2>
            <div className="flex gap-3">
              <input
                type="text"
                value={orgName}
                onChange={(e) => setOrgName(e.target.value)}
                className="flex-1 border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <button
                onClick={handleSaveName}
                disabled={savingName}
                className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition"
              >
                {savingName ? "Saving..." : "Save"}
              </button>
            </div>
          </div>
        )}

        {/* Members */}
        {tab === "members" && (
          <div className="bg-white border rounded-xl divide-y">
            {loadingMembers ? (
              <div className="px-6 py-8 text-center text-gray-400 animate-pulse">Loading members...</div>
            ) : (
              members.map((m) => (
                <div key={m.user_id} className="px-6 py-4 flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-gray-900">{m.full_name || m.email}</p>
                    <p className="text-xs text-gray-400">{m.email}</p>
                  </div>
                  <div className="flex items-center gap-3">
                    <select
                      value={m.role}
                      onChange={(e) => handleRoleChange(m.user_id, e.target.value)}
                      className="border rounded-lg px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
                    >
                      <option value="admin">Admin</option>
                      <option value="viewer">Viewer</option>
                    </select>
                    {m.user_id !== activeOrg?.org.owner_id && (
                      <button
                        onClick={() => handleRemoveMember(m.user_id)}
                        className="text-red-400 hover:text-red-600 text-xs transition"
                      >
                        Remove
                      </button>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        )}

        {/* Invites */}
        {tab === "invites" && (
          <div className="space-y-4">
            <div className="bg-white border rounded-xl p-5">
              <h2 className="font-semibold text-gray-800 mb-3">Generate Invite Link</h2>
              <div className="flex gap-3">
                <select
                  value={newInviteRole}
                  onChange={(e) => setNewInviteRole(e.target.value as "admin" | "viewer")}
                  className="border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="viewer">Viewer (read-only)</option>
                  <option value="admin">Admin</option>
                </select>
                <button
                  onClick={handleCreateInvite}
                  disabled={creatingInvite}
                  className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition"
                >
                  {creatingInvite ? "Generating..." : "Generate Link"}
                </button>
              </div>
              <p className="text-xs text-gray-400 mt-2">Links expire in 7 days and are single-use.</p>
            </div>

            {loadingInvites ? (
              <div className="text-center py-6 text-gray-400 animate-pulse">Loading invites...</div>
            ) : (
              <div className="bg-white border rounded-xl divide-y">
                {invites.length === 0 && (
                  <div className="px-6 py-8 text-center text-gray-400 text-sm">No active invites.</div>
                )}
                {invites.map((inv) => (
                  <div key={inv.id} className="px-5 py-4 flex items-center justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-mono text-gray-500 truncate">
                        {appUrl}/invite/{inv.token}
                      </p>
                      <p className="text-xs text-gray-400 mt-0.5">
                        Role: <span className="font-medium">{inv.role}</span> · Expires:{" "}
                        {new Date(inv.expires_at).toLocaleDateString()}
                      </p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <button
                        onClick={() => copyInviteLink(inv.token)}
                        className="text-blue-500 hover:text-blue-700 text-xs font-medium transition"
                      >
                        {copiedToken === inv.token ? "Copied!" : "Copy"}
                      </button>
                      <button
                        onClick={() => handleRevokeInvite(inv.id)}
                        className="text-red-400 hover:text-red-600 text-xs transition"
                      >
                        Revoke
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Danger Zone */}
        {tab === "danger" && (
          <div className="bg-white border border-red-200 rounded-xl p-6">
            <h2 className="font-semibold text-red-700 mb-2">Delete Organization</h2>
            <p className="text-sm text-gray-500 mb-4">
              Permanently deletes this organization, all bank accounts, transactions, and receipts. This cannot be undone.
            </p>
            <button
              onClick={handleDeleteOrg}
              className="bg-red-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-red-700 transition"
            >
              Delete Organization
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
