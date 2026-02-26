import axios from "axios";

export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
  getLinkToken: () => api.get<{ link_token: string }>("/bank/link-token"),
  connectBank: (public_token: string, institution_name?: string) =>
    api.post("/bank/connect", { public_token, institution_name }),
  getAccounts: () => api.get("/bank/accounts"),
};

export const transactionApi = {
  sync: (days_back = 90) => api.post(`/transactions/sync?days_back=${days_back}`),
  list: (params: Record<string, unknown>) =>
    api.get("/transactions/", { params }),
};

export const totalsApi = {
  getSummary: (start_date?: string, end_date?: string) =>
    api.get("/totals/", { params: { start_date, end_date } }),
  getMonthly: () => api.get("/totals/monthly"),
};

export const receiptApi = {
  downloadSingle: (transaction_id: string) =>
    api.get(`/receipts/${transaction_id}`, { responseType: "blob" }),
  downloadBatch: (start_date?: string, end_date?: string) =>
    api.post("/receipts/batch", null, {
      params: { start_date, end_date },
      responseType: "blob",
    }),
};

export default api;
