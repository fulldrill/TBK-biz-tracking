"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useOrg } from "@/context/OrgContext";

export default function OrgSwitcher() {
  const { orgs, activeOrg, setActiveOrg } = useOrg();
  const [open, setOpen] = useState(false);
  const router = useRouter();

  if (!activeOrg) return null;

  const roleBadge = (role: string) => (
    <span
      className={`text-xs px-1.5 py-0.5 rounded font-medium ${
        role === "admin"
          ? "bg-blue-100 text-blue-700"
          : "bg-gray-100 text-gray-500"
      }`}
    >
      {role}
    </span>
  );

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 border rounded-lg px-3 py-1.5 text-sm hover:bg-gray-50 transition"
      >
        <span className="font-medium text-gray-800 max-w-[160px] truncate">
          {activeOrg.org.name}
        </span>
        {roleBadge(activeOrg.role)}
        <svg className="w-3 h-3 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open && (
        <div className="absolute right-0 mt-1 w-64 bg-white rounded-xl shadow-lg border z-50">
          <div className="py-1">
            {orgs.map((u) => (
              <button
                key={u.org.id}
                onClick={() => {
                  setActiveOrg(u);
                  setOpen(false);
                }}
                className={`w-full text-left px-4 py-2.5 hover:bg-gray-50 flex items-center justify-between transition ${
                  u.org.id === activeOrg.org.id ? "bg-blue-50" : ""
                }`}
              >
                <span className="text-sm text-gray-800 truncate">{u.org.name}</span>
                {roleBadge(u.role)}
              </button>
            ))}
            <div className="border-t mt-1 pt-1">
              <button
                onClick={() => {
                  setOpen(false);
                  router.push("/orgs");
                }}
                className="w-full text-left px-4 py-2.5 text-sm text-blue-600 hover:bg-gray-50 transition"
              >
                + New Organization
              </button>
              <button
                onClick={() => {
                  setOpen(false);
                  router.push(`/orgs/${activeOrg.org.id}/settings`);
                }}
                className="w-full text-left px-4 py-2.5 text-sm text-gray-600 hover:bg-gray-50 transition"
              >
                Org Settings
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
