import type { Metadata } from "next";
import "./globals.css";
import { OrgProvider } from "@/context/OrgContext";

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
      <body>
        <OrgProvider>{children}</OrgProvider>
      </body>
    </html>
  );
}
