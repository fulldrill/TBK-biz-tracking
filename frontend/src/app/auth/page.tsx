"use client";
import { useState, useEffect, useCallback, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { authApi, checkHealth, getErrorMessage, API_BASE } from "@/lib/api";
import { useOrg } from "@/context/OrgContext";

function AuthForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { orgs, refreshOrgs } = useOrg();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [form, setForm] = useState({ email: "", password: "", full_name: "", totp_code: "" });
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(false);
  const [totpSecret, setTotpSecret] = useState("");
  const [backendStatus, setBackendStatus] = useState<"checking" | "connected" | "disconnected">("checking");

  const runHealthCheck = useCallback(async () => {
    setBackendStatus("checking");
    const healthy = await checkHealth();
    setBackendStatus(healthy ? "connected" : "disconnected");
  }, []);

  useEffect(() => {
    runHealthCheck();
  }, [runHealthCheck]);

  const validate = (): string | null => {
    if (mode === "register" && !form.full_name.trim()) {
      return "Full name is required.";
    }
    if (!form.email.trim()) {
      return "Email is required.";
    }
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(form.email)) {
      return "Please enter a valid email address.";
    }
    if (!form.password) {
      return "Password is required.";
    }
    if (form.password.length < 8) {
      return "Password must be at least 8 characters.";
    }
    return null;
  };

  const handleSubmit = async () => {
    setError("");
    setSuccess("");
    const validationError = validate();
    if (validationError) {
      setError(validationError);
      return;
    }
    setLoading(true);
    try {
      if (mode === "register") {
        const res = await authApi.register({
          email: form.email,
          password: form.password,
          full_name: form.full_name,
        });
        setTotpSecret(res.data.totp_secret);
        setSuccess("Account created successfully! Save your 2FA secret below, then sign in.");
        setForm({ email: form.email, password: "", full_name: "", totp_code: "" });
        setMode("login");
      } else {
        const res = await authApi.login({
          email: form.email,
          password: form.password,
          totp_code: form.totp_code || undefined,
        });
        localStorage.setItem("access_token", res.data.access_token);
        await refreshOrgs();
        // Handle pending invite redirect
        const next = searchParams.get("next");
        const pendingToken = typeof window !== "undefined"
          ? sessionStorage.getItem("pending_invite_token")
          : null;
        if (next) {
          router.push(next);
        } else if (pendingToken) {
          sessionStorage.removeItem("pending_invite_token");
          router.push(`/invite/${pendingToken}`);
        } else if (orgs.length > 1) {
          router.push("/orgs");
        } else {
          router.push("/dashboard");
        }
      }
    } catch (err: unknown) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 to-blue-900 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-8">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-gray-900">BizTrack</h1>
          <p className="text-gray-500 mt-1">Business Financial Tracking</p>
        </div>

        {/* Backend connection status */}
        <div className="flex items-center justify-between mb-4 text-xs text-gray-500">
          <span className="flex items-center gap-1.5">
            <span
              className={`inline-block w-2 h-2 rounded-full ${
                backendStatus === "connected"
                  ? "bg-green-500"
                  : backendStatus === "disconnected"
                  ? "bg-red-500"
                  : "bg-yellow-400 animate-pulse"
              }`}
            />
            {backendStatus === "connected"
              ? "Backend connected"
              : backendStatus === "disconnected"
              ? "Backend unreachable"
              : "Checking connection…"}
          </span>
          <button
            onClick={runHealthCheck}
            className="text-blue-500 hover:underline"
          >
            Test connection
          </button>
        </div>
        {backendStatus === "disconnected" && (
          <div className="bg-orange-50 border border-orange-200 text-orange-700 text-xs rounded-lg px-3 py-2 mb-4">
            Cannot reach <code className="font-mono">{API_BASE}</code>. Ensure the backend is
            running and <code className="font-mono">NEXT_PUBLIC_API_URL</code> is set correctly.
          </div>
        )}

        {totpSecret && (
          <div className="bg-yellow-50 border border-yellow-200 rounded-xl p-4 mb-6">
            <p className="text-sm font-semibold text-yellow-800 mb-1">Save your 2FA Secret</p>
            <p className="text-xs text-yellow-700 mb-2">
              Scan this in Google Authenticator or save the key:
            </p>
            <code className="block text-xs bg-yellow-100 p-2 rounded break-all">{totpSecret}</code>
            <p className="text-xs text-yellow-600 mt-2">Now log in below.</p>
          </div>
        )}

        <div className="flex rounded-lg border mb-6 overflow-hidden">
          <button
            onClick={() => setMode("login")}
            className={`flex-1 py-2 text-sm font-medium transition ${mode === "login" ? "bg-blue-600 text-white" : "bg-white text-gray-600 hover:bg-gray-50"}`}
          >
            Sign In
          </button>
          <button
            onClick={() => setMode("register")}
            className={`flex-1 py-2 text-sm font-medium transition ${mode === "register" ? "bg-blue-600 text-white" : "bg-white text-gray-600 hover:bg-gray-50"}`}
          >
            Register
          </button>
        </div>

        <div className="space-y-4">
          {mode === "register" && (
            <input
              type="text"
              placeholder="Full Name"
              value={form.full_name}
              onChange={(e) => setForm((f) => ({ ...f, full_name: e.target.value }))}
              className="w-full border rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          )}
          <input
            type="email"
            placeholder="Email address"
            value={form.email}
            onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
            className="w-full border rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <input
            type="password"
            placeholder="Password"
            value={form.password}
            onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
            className="w-full border rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          {mode === "login" && (
            <input
              type="text"
              placeholder="2FA Code (optional)"
              value={form.totp_code}
              onChange={(e) => setForm((f) => ({ ...f, totp_code: e.target.value }))}
              className="w-full border rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          )}

          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg px-4 py-2">
              {error}
            </div>
          )}

          {success && (
            <div className="bg-green-50 border border-green-200 text-green-700 text-sm rounded-lg px-4 py-2">
              {success}
            </div>
          )}

          <button
            onClick={handleSubmit}
            disabled={loading}
            className="w-full bg-blue-600 text-white rounded-lg py-2.5 font-medium hover:bg-blue-700 disabled:opacity-50 transition"
          >
            {loading ? "Processing..." : mode === "login" ? "Sign In" : "Create Account"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function AuthPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-gradient-to-br from-slate-900 to-blue-900" />}>
      <AuthForm />
    </Suspense>
  );
}
