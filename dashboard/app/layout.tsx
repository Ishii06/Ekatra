import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Ekatra — Adaptive Multi-Agent Orchestration",
  description:
    "Presentation dashboard for Ekatra, an adaptive multi-agent orchestration framework for autonomous software development.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="min-h-screen">{children}</body>
    </html>
  );
}