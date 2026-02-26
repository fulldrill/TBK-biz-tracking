import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "BizTrack Receipts",
  description: "Financial tracking with Plaid bank integration",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
