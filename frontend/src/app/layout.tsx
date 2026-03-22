import type { Metadata } from "next";
import "./globals.css";
import { OrgProvider } from "@/context/OrgContext";
import WeshChat from "@/components/WeshChat";

export const metadata: Metadata = {
  title: "Clerq",
  description: "Business financial tracking with Plaid bank integration",
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
        <WeshChat />
      </body>
    </html>
  );
}
