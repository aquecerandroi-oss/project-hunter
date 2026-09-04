import "./globals.css";

import { ClerkProvider } from "@clerk/nextjs";
import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Project Hunter",
  description: "Encontre assimetrias com risco controlado.",
};

// Applies the persisted theme before paint, avoiding a flash of the wrong
// theme. Kept inline (not a bundled script) so it runs synchronously before
// first render; it never touches anything but `data-theme` and its own key.
const THEME_INIT_SCRIPT = `(function(){try{var t=localStorage.getItem("hunter-theme");if(t==="light"||t==="dark"){document.documentElement.setAttribute("data-theme",t);}}catch(e){}})();`;

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <ClerkProvider>
      <html lang="pt-BR" suppressHydrationWarning>
        <head>
          <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
        </head>
        <body className="min-h-dvh bg-background font-sans text-foreground antialiased">{children}</body>
      </html>
    </ClerkProvider>
  );
}
