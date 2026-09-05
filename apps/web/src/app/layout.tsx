import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "EvalOps Evidence Console",
  description: "Static, read-only evidence from the EvalOps Lab public contract.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>{children}</body>
    </html>
  );
}
