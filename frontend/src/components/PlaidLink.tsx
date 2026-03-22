"use client";
import { usePlaidLink } from "react-plaid-link";
import { useEffect, useState } from "react";
import { bankApi } from "@/lib/api";

interface Props {
  orgId: string;
  onSuccess: () => void;
}

export default function PlaidLinkButton({ orgId, onSuccess }: Props) {
  const [linkToken, setLinkToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    bankApi
      .getLinkToken(orgId)
      .then((res) => setLinkToken(res.data.link_token))
      .catch(() => setError("Failed to initialize bank connection. Check your Plaid keys."));
  }, [orgId]);

  const { open, ready } = usePlaidLink({
    token: linkToken || "",
    onSuccess: async (public_token, metadata) => {
      setLoading(true);
      try {
        await bankApi.connectBank(orgId, public_token, metadata.institution?.name);
        onSuccess();
      } catch {
        setError("Failed to connect bank account.");
      } finally {
        setLoading(false);
      }
    },
    onExit: (err) => {
      if (err) setError("Bank connection cancelled or failed.");
    },
  });

  if (error) {
    return <span className="text-red-500 text-xs">{error}</span>;
  }

  return (
    <button
      onClick={() => open()}
      disabled={!ready || loading}
      className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 transition text-sm font-medium"
    >
      {loading ? "Connecting..." : "Connect Bank Account"}
    </button>
  );
}
