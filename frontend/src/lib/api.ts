import axios from "axios";

function resolveApiBase(): string {
  const configured = process.env.NEXT_PUBLIC_API_URL?.trim();

  if (typeof window !== "undefined") {
    if (!configured) {
      return `${window.location.protocol}//${window.location.hostname}:8000`;
    }

    try {
      const parsed = new URL(configured);
      const pageHost = window.location.hostname;
      const isLocalConfiguredHost = parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1";
      const isLocalPageHost = pageHost === "localhost" || pageHost === "127.0.0.1";

      if (isLocalConfiguredHost && !isLocalPageHost) {
        parsed.hostname = pageHost;
        return parsed.toString().replace(/\/$/, "");
      }
    } catch {
      return configured;
    }

    return configured;
  }

  return configured || "http://localhost:8000";
}

export const API_BASE = resolveApiBase();

const api = axios.create({ baseURL: API_BASE });

api.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("access_token");
    if (token) config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401 && typeof window !== "undefined") {
      localStorage.removeItem("access_token");
      window.location.href = "/auth";
    }
    // Enrich network errors with more context before rejecting
    if (!err.response) {
      const url = err.config?.baseURL || API_BASE;
      console.error(`[API] Network error reaching ${url}:`, err.message, err.code);
    } else {
      console.error(`[API] Error ${err.response.status}:`, err.response.data);
    }
    return Promise.reject(err);
  }
);

/** Check whether the backend is reachable. Returns true if healthy. */
export async function checkHealth(): Promise<boolean> {
  try {
    await axios.get(`${API_BASE}/health`, { timeout: 5000 });
    return true;
  } catch {
    return false;
  }
}

/** Translate an axios error into a user-friendly message. */
export function getErrorMessage(err: unknown): string {
  if (!axios.isAxiosError(err)) {
    return err instanceof Error ? err.message : "An unexpected error occurred.";
  }
  if (err.response) {
    // Backend returned an error response
    const detail = err.response.data?.detail;
    if (detail) return detail;
    return `Server error (${err.response.status}). Please try again.`;
  }
  // No response – network-level failure
  const code = err.code;
  if (code === "ERR_NETWORK" || code === "ERR_CONNECTION_REFUSED") {
    return `Cannot reach the server at ${API_BASE}. Make sure the backend is running.`;
  }
  if (code === "ECONNABORTED") {
    return `Request timed out. The server at ${API_BASE} is not responding.`;
  }
  if (err.message?.toLowerCase().includes("cors")) {
    return `CORS error: the server at ${API_BASE} is blocking requests from this origin.`;
  }
  return `Network error: ${err.message || "unable to connect to the server."}`;
}

export const authApi = {
  register: (data: { email: string; password: string; full_name?: string }) =>
    api.post("/auth/register", data),
  login: (data: { email: string; password: string; totp_code?: string }) =>
    api.post("/auth/login", data),
};

export const bankApi = {
  getLinkToken: (orgId: string) =>
    api.get<{ link_token: string }>(`/orgs/${orgId}/bank/link-token`),
  connectBank: (orgId: string, public_token: string, institution_name?: string) =>
    api.post(`/orgs/${orgId}/bank/connect`, { public_token, institution_name }),
  getAccounts: (orgId: string) => api.get(`/orgs/${orgId}/bank/accounts`),
};

export const transactionApi = {
  sync: (orgId: string, days_back = 90) =>
    api.post(`/orgs/${orgId}/transactions/sync?days_back=${days_back}`),
  list: (orgId: string, params: Record<string, unknown>) =>
    api.get(`/orgs/${orgId}/transactions/`, { params }),
};

export const totalsApi = {
  getSummary: (orgId: string, start_date?: string, end_date?: string) =>
    api.get(`/orgs/${orgId}/totals/`, { params: { start_date, end_date } }),
  getMonthly: (orgId: string) => api.get(`/orgs/${orgId}/totals/monthly`),
};

export const receiptApi = {
  downloadSingle: (orgId: string, transaction_id: string) =>
    api.get(`/orgs/${orgId}/receipts/${transaction_id}`, { responseType: "blob" }),
  downloadBatch: (orgId: string, start_date?: string, end_date?: string) =>
    api.post(`/orgs/${orgId}/receipts/batch`, null, {
      params: { start_date, end_date },
      responseType: "blob",
    }),
};

export const orgApi = {
  list: () => api.get("/orgs/"),
  create: (name: string) => api.post("/orgs/", { name }),
  get: (orgId: string) => api.get(`/orgs/${orgId}`),
  update: (orgId: string, name: string) => api.patch(`/orgs/${orgId}`, { name }),
  delete: (orgId: string) => api.delete(`/orgs/${orgId}`),
  getMembers: (orgId: string) => api.get(`/orgs/${orgId}/members`),
  updateMemberRole: (orgId: string, userId: string, role: string) =>
    api.patch(`/orgs/${orgId}/members/${userId}`, { role }),
  removeMember: (orgId: string, userId: string) =>
    api.delete(`/orgs/${orgId}/members/${userId}`),
  createInvite: (orgId: string, role: string, expires_hours = 168) =>
    api.post(`/orgs/${orgId}/invites`, { role, expires_hours }),
  listInvites: (orgId: string) => api.get(`/orgs/${orgId}/invites`),
  revokeInvite: (orgId: string, inviteId: string) =>
    api.delete(`/orgs/${orgId}/invites/${inviteId}`),
};

export const inviteApi = {
  preview: (token: string) => api.get(`/invites/${token}`),
  redeem: (token: string) => api.post(`/invites/${token}/redeem`),
};

export default api;
