import type { Metadata } from "next";
import { Providers } from "@/components/providers";
import "./globals.css";

// Nonce-based CSP needs a fresh nonce per request, so pages must render dynamically.
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "ResearchOS — Evidence over intuition",
  description:
    "A controlled AI research workspace. Plan, retrieve, analyze and verify with source-backed intelligence.",
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
