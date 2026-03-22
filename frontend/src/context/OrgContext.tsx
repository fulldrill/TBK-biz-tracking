"use client";

import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { UserOrg, OrgRole } from "@/types";
import { orgApi } from "@/lib/api";

interface OrgContextValue {
  orgs: UserOrg[];
  activeOrg: UserOrg | null;
  activeRole: OrgRole | null;
  isAdmin: boolean;
  isLoading: boolean;
  setActiveOrg: (org: UserOrg) => void;
  refreshOrgs: () => Promise<void>;
}

const OrgContext = createContext<OrgContextValue | null>(null);

export function OrgProvider({ children }: { children: React.ReactNode }) {
  const [orgs, setOrgs] = useState<UserOrg[]>([]);
  const [activeOrg, setActiveOrgState] = useState<UserOrg | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const refreshOrgs = useCallback(async () => {
    const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
    if (!token) {
      setIsLoading(false);
      return;
    }
    try {
      const res = await orgApi.list();
      const fetched: UserOrg[] = res.data;
      setOrgs(fetched);

      const savedId = typeof window !== "undefined"
        ? localStorage.getItem("active_org_id")
        : null;

      const found = savedId ? fetched.find((u) => u.org.id === savedId) : null;
      if (found) {
        setActiveOrgState(found);
      } else if (fetched.length === 1) {
        setActiveOrgState(fetched[0]);
        localStorage.setItem("active_org_id", fetched[0].org.id);
      } else if (fetched.length > 1 && !found) {
        // Will let the dashboard/orgs page handle redirection
        setActiveOrgState(null);
      }
    } catch {
      // Not authenticated yet — no-op
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshOrgs();
  }, [refreshOrgs]);

  const setActiveOrg = useCallback((org: UserOrg) => {
    setActiveOrgState(org);
    if (typeof window !== "undefined") {
      localStorage.setItem("active_org_id", org.org.id);
    }
  }, []);

  const activeRole = activeOrg?.role ?? null;
  const isAdmin = activeRole === "admin";

  return (
    <OrgContext.Provider
      value={{ orgs, activeOrg, activeRole, isAdmin, isLoading, setActiveOrg, refreshOrgs }}
    >
      {children}
    </OrgContext.Provider>
  );
}

export function useOrg(): OrgContextValue {
  const ctx = useContext(OrgContext);
  if (!ctx) throw new Error("useOrg must be used within OrgProvider");
  return ctx;
}
