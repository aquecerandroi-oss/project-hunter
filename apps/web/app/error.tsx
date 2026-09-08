"use client";

import Link from "next/link";
import { useEffect } from "react";

import { Button } from "@/components/ui/button";
import { logger } from "@/lib/logger";

export interface RootRouteErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

/**
 * Route-segment error boundary for everything directly under `app/`
 * (brief T3.28b): `app/page.tsx` (the `/` home redirect) calls `me()`
 * directly and uncaught -- a 429/5xx there used to fall through all the way
 * to Next's bare "Application error" screen since nothing above it (this
 * boundary didn't exist) or below it (there is nothing below `/`) ever got
 * a chance to render something honest. Mirrors
 * `(app)/[orgSlug]/error.tsx`'s shape (same copy, same "no stack trace on
 * screen" rule) minus the org-scoped "Ver System" link, since a failure
 * this early has no `orgSlug` to link with yet.
 */
export default function RootRouteError({ error, reset }: RootRouteErrorProps) {
  useEffect(() => {
    logger.error("root_route_render_failed", { error: error.message, digest: error.digest });
  }, [error]);

  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-3 bg-bg p-10 text-center text-fg">
      <p className="text-sm text-fg">Não foi possível continuar: {error.message}</p>
      <div className="flex flex-wrap items-center justify-center gap-2">
        <Button type="button" variant="outline" size="sm" onClick={() => reset()}>
          Tentar novamente
        </Button>
        <Button asChild type="button" variant="ghost" size="sm">
          <Link href="/">Voltar ao início</Link>
        </Button>
      </div>
    </div>
  );
}
