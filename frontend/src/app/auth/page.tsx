"use client";
import { useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { authApi, getErrorMessage } from "@/lib/api";
import { useOrg } from "@/context/OrgContext";

const features = [
  {
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M3 6l3 1m0 0l-3 9a5.002 5.002 0 006.001 0M6 7l3 9M6 7l6-2m6 2l3-1m-3 1l-3 9a5.002 5.002 0 006.001 0M18 7l3 9m-3-9l-6-2m0-2v2m0 16V5m0 16H9m3 0h3" />
      </svg>
    ),
    title: "Bank-connected tracking",
    desc: "Sync transactions from any bank via Plaid. Real-time, automatic, always up to date.",
  },
  {
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    ),
    title: "Multi-org & roles",
    desc: "Manage separate books per business. Invite accountants with read-only access.",
  },
  {
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
    ),
    title: "PDF receipts on demand",
    desc: "Generate individual or batch PDF receipts for any date range instantly.",
  },
];

function EyeIcon({ open }: { open: boolean }) {
  return open ? (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
    </svg>
  ) : (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
    </svg>
  );
}

function AuthForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { orgs, refreshOrgs } = useOrg();

  const [mode, setMode] = useState<"login" | "register">("login");
  const [form, setForm] = useState({ email: "", password: "", full_name: "", totp_code: "" });
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(false);
  const [totpSecret, setTotpSecret] = useState("");

  const validate = (): string | null => {
    if (mode === "register" && !form.full_name.trim()) return "Full name is required.";
    if (!form.email.trim()) return "Email is required.";
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) return "Please enter a valid email address.";
    if (!form.password) return "Password is required.";
    if (form.password.length < 8) return "Password must be at least 8 characters.";
    return null;
  };

  const handleSubmit = async () => {
    setError("");
    setSuccess("");
    const validationError = validate();
    if (validationError) { setError(validationError); return; }
    setLoading(true);
    try {
      if (mode === "register") {
        const res = await authApi.register({ email: form.email, password: form.password, full_name: form.full_name });
        setTotpSecret(res.data.totp_secret);
        setSuccess("Account created! Save your 2FA secret below, then sign in.");
        setForm({ email: form.email, password: "", full_name: "", totp_code: "" });
        setMode("login");
      } else {
        const res = await authApi.login({ email: form.email, password: form.password, totp_code: form.totp_code || undefined });
        localStorage.setItem("access_token", res.data.access_token);
        await refreshOrgs();
        const next = searchParams.get("next");
        const pendingToken = typeof window !== "undefined" ? sessionStorage.getItem("pending_invite_token") : null;
        if (next) router.push(next);
        else if (pendingToken) { sessionStorage.removeItem("pending_invite_token"); router.push(`/invite/${pendingToken}`); }
        else if (orgs.length > 1) router.push("/orgs");
        else router.push("/dashboard");
      }
    } catch (err: unknown) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  const switchMode = (m: "login" | "register") => {
    setMode(m);
    setError("");
    setSuccess("");
    setShowPassword(false);
  };

  return (
    <div className="min-h-screen bg-[#0a0f1e] text-white overflow-x-hidden">

      {/* Ambient background blobs */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute -top-40 -left-40 w-[600px] h-[600px] rounded-full bg-blue-700/20 blur-[120px]" />
        <div className="absolute top-1/3 right-0 w-[500px] h-[500px] rounded-full bg-indigo-600/15 blur-[100px]" />
        <div className="absolute bottom-0 left-1/3 w-[400px] h-[400px] rounded-full bg-cyan-500/10 blur-[90px]" />
      </div>

      {/* Navbar */}
      <nav className="relative z-10 flex items-center px-6 md:px-12 py-5 border-b border-white/5">
        <span className="text-xl font-bold tracking-tight">Clerq</span>
      </nav>

      {/* Main layout */}
      <div className="relative z-10 max-w-7xl mx-auto px-6 md:px-12 py-12 lg:py-20">
        <div className="flex flex-col lg:flex-row lg:items-start gap-16 lg:gap-12">

          {/* ── Left: Hero + Features ── */}
          <div className="flex-1 max-w-xl">
            {/* Badge */}
            <div className="inline-flex items-center gap-2 bg-blue-500/10 border border-blue-500/20 rounded-full px-4 py-1.5 text-xs text-blue-300 font-medium mb-8">
              <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
              Built for small business owners
            </div>

            <h1 className="text-4xl md:text-5xl lg:text-6xl font-bold leading-tight tracking-tight mb-6">
              Your finances,{" "}
              <span className="bg-gradient-to-r from-blue-400 to-cyan-300 bg-clip-text text-transparent">
                under control.
              </span>
            </h1>

            <p className="text-lg text-white/50 leading-relaxed mb-10 max-w-md">
              Clerq connects to your bank, automatically categorizes transactions, detects Zelle transfers, and lets you share access with your accountant — all in one place.
            </p>

            {/* Stats */}
            <div className="flex gap-8 mb-12">
              {[
                { value: "90 days", label: "of history synced" },
                { value: "2FA", label: "security built-in" },
                { value: "PDF", label: "receipts on demand" },
              ].map((s) => (
                <div key={s.label}>
                  <p className="text-2xl font-bold text-white">{s.value}</p>
                  <p className="text-xs text-white/40 mt-0.5">{s.label}</p>
                </div>
              ))}
            </div>

            {/* Feature cards */}
            <div className="space-y-4">
              {features.map((f) => (
                <div key={f.title} className="flex items-start gap-4 p-4 rounded-xl bg-white/[0.03] border border-white/[0.06] hover:bg-white/[0.06] transition-colors">
                  <div className="shrink-0 w-9 h-9 rounded-lg bg-blue-500/15 flex items-center justify-center text-blue-400">
                    {f.icon}
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-white/90">{f.title}</p>
                    <p className="text-xs text-white/45 mt-0.5 leading-relaxed">{f.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* ── Right: Auth Card ── */}
          <div className="w-full lg:w-[400px] lg:sticky lg:top-8">
            <div className="rounded-2xl bg-white/[0.04] border border-white/10 backdrop-blur-xl p-8 shadow-2xl shadow-black/40">

              {/* TOTP secret banner */}
              {totpSecret && (
                <div className="bg-amber-500/10 border border-amber-500/20 rounded-xl p-4 mb-6">
                  <p className="text-sm font-semibold text-amber-300 mb-1">Save your 2FA Secret</p>
                  <p className="text-xs text-amber-300/70 mb-2">Scan in Google Authenticator or copy the key:</p>
                  <code className="block text-xs bg-black/30 text-amber-200 p-2.5 rounded-lg break-all">{totpSecret}</code>
                  <p className="text-xs text-amber-300/60 mt-2">Sign in below once saved.</p>
                </div>
              )}

              {/* Tabs */}
              <div className="flex bg-white/5 rounded-xl p-1 mb-6">
                {(["login", "register"] as const).map((m) => (
                  <button
                    key={m}
                    onClick={() => switchMode(m)}
                    className={`flex-1 py-2 text-sm font-medium rounded-lg transition-all duration-200 ${
                      mode === m
                        ? "bg-blue-600 text-white shadow-lg shadow-blue-600/30"
                        : "text-white/50 hover:text-white/80"
                    }`}
                  >
                    {m === "login" ? "Sign In" : "Register"}
                  </button>
                ))}
              </div>

              <div className="space-y-3">
                {/* Full name (register only) */}
                {mode === "register" && (
                  <input
                    type="text"
                    placeholder="Full name"
                    value={form.full_name}
                    onChange={(e) => setForm((f) => ({ ...f, full_name: e.target.value }))}
                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white placeholder-white/30 focus:outline-none focus:ring-2 focus:ring-blue-500/60 focus:border-transparent transition"
                  />
                )}

                {/* Email */}
                <input
                  type="email"
                  placeholder="Email address"
                  value={form.email}
                  onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
                  onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
                  className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white placeholder-white/30 focus:outline-none focus:ring-2 focus:ring-blue-500/60 focus:border-transparent transition"
                />

                {/* Password with show/hide */}
                <div className="relative">
                  <input
                    type={showPassword ? "text" : "password"}
                    placeholder="Password"
                    value={form.password}
                    onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
                    onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 pr-11 text-sm text-white placeholder-white/30 focus:outline-none focus:ring-2 focus:ring-blue-500/60 focus:border-transparent transition"
                  />
                  <button
                    type="button"
                    aria-label={showPassword ? "Hide password" : "Show password"}
                    onClick={() => setShowPassword((v) => !v)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-white/30 hover:text-white/70 transition-colors"
                  >
                    <EyeIcon open={showPassword} />
                  </button>
                </div>

                {/* 2FA (login only) */}
                {mode === "login" && (
                  <input
                    type="text"
                    inputMode="numeric"
                    placeholder="2FA code (optional)"
                    value={form.totp_code}
                    onChange={(e) => setForm((f) => ({ ...f, totp_code: e.target.value }))}
                    onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white placeholder-white/30 focus:outline-none focus:ring-2 focus:ring-blue-500/60 focus:border-transparent transition"
                  />
                )}

                {/* Error */}
                {error && (
                  <div className="flex items-start gap-2 bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-2.5">
                    <svg className="w-4 h-4 text-red-400 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                    <p className="text-xs text-red-300">{error}</p>
                  </div>
                )}

                {/* Success */}
                {success && (
                  <div className="flex items-start gap-2 bg-emerald-500/10 border border-emerald-500/20 rounded-xl px-4 py-2.5">
                    <svg className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                    <p className="text-xs text-emerald-300">{success}</p>
                  </div>
                )}

                {/* Submit */}
                <button
                  onClick={handleSubmit}
                  disabled={loading}
                  className="w-full bg-blue-600 hover:bg-blue-500 active:bg-blue-700 text-white rounded-xl py-2.5 text-sm font-semibold transition-all duration-150 shadow-lg shadow-blue-600/25 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {loading ? (
                    <span className="flex items-center justify-center gap-2">
                      <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                      </svg>
                      Processing…
                    </span>
                  ) : mode === "login" ? "Sign In" : "Create Account"}
                </button>
              </div>

              <p className="text-center text-xs text-white/25 mt-5">
                {mode === "login" ? "Don't have an account? " : "Already have an account? "}
                <button onClick={() => switchMode(mode === "login" ? "register" : "login")} className="text-blue-400 hover:text-blue-300 transition-colors">
                  {mode === "login" ? "Register" : "Sign in"}
                </button>
              </p>
            </div>

            <p className="text-center text-xs text-white/20 mt-4">
              Secured with JWT · 2FA optional · Bank data via Plaid
            </p>
          </div>

        </div>
      </div>
    </div>
  );
}

export default function AuthPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-[#0a0f1e]" />}>
      <AuthForm />
    </Suspense>
  );
}
