"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect } from "react";

import { Button } from "@/components/ui/button";
import { logger } from "@/lib/logger";

export interface RouteErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

/**
 * Route-segment error boundary for every page under `(app)/[orgSlug]/**`
 * (T3.24a's brief §3, fixes X1): before this file existed, a render failure
 * fell through to Next's own English default error screen with a stack
 * trace. Portuguese, no stack trace, same dashed-red-border shape as
 * `radar-error.tsx`/`lab-error.tsx`. `reset()` re-renders the segment in
 * place; "Ver System" is an escape hatch to the one page that reports
 * infra health directly, for when the failure is not this page's own bug.
 */
export default function OrgSegmentError({ error, reset }: RouteErrorProps) {
  const params = useParams<{ orgSlug: string }>();

  useEffect(() => {
    logger.error("route_render_failed", { error: error.message, digest: error.digest });
  }, [error]);

  return (
    <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-red/40 bg-bg-elevated p-10 text-center">
      <p className="text-sm text-fg">Esta tela falhou ao renderizar: {error.message}</p>
      <div className="flex flex-wrap items-center justify-center gap-2">
        <Button type="button" variant="outline" size="sm" onClick={() => reset()}>
          Tentar novamente
        </Button>
        <Button asChild type="button" variant="ghost" size="sm">
          <Link href={`/${params.orgSlug}/system`}>Ver System</Link>
        </Button>
      </div>
    </div>
  );
}
