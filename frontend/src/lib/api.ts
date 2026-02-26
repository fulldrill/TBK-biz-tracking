import axios from "axios";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
    return Promise.reject(err);
  }
);

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
