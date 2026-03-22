"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function Home() {
  const router = useRouter();
  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (token) {
      router.push("/dashboard");
    } else {
      router.push("/auth");
    }
  }, [router]);
  return (
    <div className="flex items-center justify-center min-h-screen">
      <p className="text-gray-500">Loading Clerq...</p>
    </div>
  );
}
