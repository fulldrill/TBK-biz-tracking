"use client";
import { useEffect, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import { inviteApi } from "@/lib/api";
import { InvitePreview } from "@/types";
import { useOrg } from "@/context/OrgContext";

export default function InvitePage() {
  const params = useParams();
  const token = params.token as string;
  const router = useRouter();
  const { refreshOrgs, orgs, setActiveOrg } = useOrg();

  const [preview, setPreview] = useState<InvitePreview | null>(null);
  const [error, setError] = useState("");
  const [redeeming, setRedeeming] = useState(false);
  const [isLoggedIn, setIsLoggedIn] = useState(false);

  useEffect(() => {
    const jwt = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
    setIsLoggedIn(!!jwt);

    inviteApi.preview(token).then((r) => {
      setPreview(r.data);
    }).catch(() => {
      setError("This invite link is invalid, expired, or has already been used.");
    });
  }, [token]);

  const handleRedeem = async () => {
    setRedeeming(true);
    try {
      const res = await inviteApi.redeem(token);
      await refreshOrgs();
      const newOrg = orgs.find((u) => u.org.id === res.data.org_id);
      if (newOrg) setActiveOrg(newOrg);
      router.push("/dashboard");
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(msg || "Failed to join organization.");
      setRedeeming(false);
    }
  };

  const handleLoginRedirect = () => {
    if (typeof window !== "undefined") {
      sessionStorage.setItem("pending_invite_token", token);
    }
    router.push(`/auth?next=/invite/${token}`);
  };

  if (error) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center p-6">
        <div className="text-center max-w-sm">
          <p className="text-red-500 font-medium mb-4">{error}</p>
          <button
            onClick={() => router.push("/dashboard")}
            className="text-blue-600 text-sm hover:underline"
          >
            Go to Dashboard
          </button>
        </div>
      </div>
    );
  }

  if (!preview) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="animate-pulse text-gray-400">Loading invite...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-6">
      <div className="bg-white border rounded-2xl p-8 max-w-sm w-full text-center shadow-sm">
        <div className="w-12 h-12 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-4">
          <svg className="w-6 h-6 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
        </div>

        <h1 className="text-xl font-bold text-gray-900 mb-1">You&apos;ve been invited</h1>
        <p className="text-gray-500 text-sm mb-6">
          Join <span className="font-semibold text-gray-800">{preview.org_name}</span> as a{" "}
          <span className={`font-medium ${preview.role === "admin" ? "text-blue-600" : "text-gray-700"}`}>
            {preview.role}
          </span>
          .
        </p>

        <p className="text-xs text-gray-400 mb-6">
          Expires {new Date(preview.expires_at).toLocaleDateString()}
        </p>

        {isLoggedIn ? (
          <button
            onClick={handleRedeem}
            disabled={redeeming}
            className="w-full bg-blue-600 text-white py-2.5 rounded-xl text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition"
          >
            {redeeming ? "Joining..." : `Join ${preview.org_name}`}
          </button>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-gray-500">Sign in or create an account to accept this invite.</p>
            <button
              onClick={handleLoginRedirect}
              className="w-full bg-blue-600 text-white py-2.5 rounded-xl text-sm font-medium hover:bg-blue-700 transition"
            >
              Sign in / Register
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
