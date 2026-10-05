import type { Metadata } from "next";
import { Providers } from "@/components/providers";
import "./globals.css";
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
