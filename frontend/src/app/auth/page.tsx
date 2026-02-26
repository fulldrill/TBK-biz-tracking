"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { authApi } from "@/lib/api";

export default function AuthPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [form, setForm] = useState({ email: "", password: "", full_name: "", totp_code: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [totpSecret, setTotpSecret] = useState("");

  const handleSubmit = async () => {
    setError("");
    setLoading(true);
    try {
      if (mode === "register") {
        const res = await authApi.register({
          email: form.email,
          password: form.password,
          full_name: form.full_name,
        });
        setTotpSecret(res.data.totp_secret);
        setMode("login");
      } else {
        const res = await authApi.login({
          email: form.email,
          password: form.password,
          totp_code: form.totp_code || undefined,
        });
        localStorage.setItem("access_token", res.data.access_token);
        router.push("/dashboard");
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Authentication failed. Check your credentials.";
      setError(message);
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
