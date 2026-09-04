import "./globals.css";

import { ClerkProvider } from "@clerk/nextjs";
import type { Metadata } from "next";
import type { ReactNode } from "react";

import { PRE_HYDRATION_SCRIPT } from "@/lib/pre-hydration-script";

export const metadata: Metadata = {
  title: "Project Hunter",
  description: "Encontre assimetrias com risco controlado.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <ClerkProvider>
      <html lang="pt-BR" suppressHydrationWarning>
        <head>
          <script dangerouslySetInnerHTML={{ __html: PRE_HYDRATION_SCRIPT }} />
        </head>
        <body className="min-h-dvh bg-bg font-sans text-fg antialiased">{children}</body>
      </html>
    </ClerkProvider>
  );
}
