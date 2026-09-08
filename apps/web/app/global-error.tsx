"use client";

import Link from "next/link";
import { useEffect } from "react";

import { logger } from "@/lib/logger";

export interface GlobalErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

/**
 * Last-resort boundary for the whole app (brief T3.28b, D5/"sem backstage"):
 * catches whatever a route-segment `error.tsx` never got a chance to (a
 * throw from `app/layout.tsx` itself, or from anything above every other
 * boundary). Next.js requires this file to render its own `<html>`/`<body>`
 * -- it replaces the ENTIRE tree, including the root layout, so it cannot
 * assume `ClerkProvider`/Tailwind's `data-theme` toggle/any other app
 * context ran. Portuguese, one sentence, no stack trace: the `digest` is
 * the only technical detail on screen, labeled as a plain "código de
 * referência" a caller can paste back to us -- never a file path, task id
 * or internal service name (docs/DESIGN.md §2, "sem backstage na copy").
 */
export default function GlobalError({ error, reset }: GlobalErrorProps) {
  useEffect(() => {
    // `lib/logger.ts` has no imports of its own (a leaf module), so it works
    // here even though this boundary replaces the entire tree, including
    // the root layout -- nothing about a failed `ClerkProvider`/app module
    // graph above this file's own import chain is a dependency of it.
    logger.error("global_render_failed", { error: error.message, digest: error.digest });
  }, [error]);

  return (
    <html lang="pt-BR">
      <body style={{ background: "#0A0A0A", color: "#F5F5F5", fontFamily: "system-ui, sans-serif" }}>
        <div
          style={{
            display: "flex",
            minHeight: "100dvh",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: "0.75rem",
            padding: "2.5rem",
            textAlign: "center",
          }}
        >
          <h1 style={{ fontSize: "1.125rem", fontWeight: 600, margin: 0 }}>Algo deu errado.</h1>
          <p style={{ fontSize: "0.875rem", color: "#A3A3A3", margin: 0 }}>Não conseguimos carregar esta página agora.</p>
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "center", gap: "0.5rem" }}>
            <button
              type="button"
              onClick={() => reset()}
              style={{
                borderRadius: "0.375rem",
                border: "1px solid #2E2E2E",
                background: "transparent",
                color: "#F5F5F5",
                padding: "0.5rem 0.75rem",
                fontSize: "0.75rem",
                cursor: "pointer",
              }}
            >
              Tentar de novo
            </button>
            <Link
              href="/"
              style={{
                borderRadius: "0.375rem",
                background: "#F2B705",
                color: "#0A0A0A",
                padding: "0.5rem 0.75rem",
                fontSize: "0.75rem",
                textDecoration: "none",
                fontWeight: 500,
              }}
            >
              Ir para o Dashboard
            </Link>
          </div>
          {error.digest && (
            <p style={{ fontSize: "0.6875rem", color: "#828282", margin: 0 }}>código de referência: {error.digest}</p>
          )}
        </div>
      </body>
    </html>
  );
}
