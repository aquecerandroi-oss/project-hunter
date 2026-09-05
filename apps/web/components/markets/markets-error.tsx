"use client";

import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";

export interface MarketsErrorProps {
  reason: string;
}

/**
 * Full-width honest failure state (docs/plans/M1.md T1.5): the API is down
 * or unreachable, so the page shows why instead of a stale-looking table --
 * CLAUDE.md's "no fake anything" extends to never rendering old numbers as
 * if they were current.
 */
export function MarketsError({ reason }: MarketsErrorProps) {
  const router = useRouter();
  return (
    <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-red/40 bg-bg-elevated p-10 text-center">
      <p className="text-sm text-fg">Mercados indisponíveis: {reason}</p>
      <Button type="button" variant="outline" size="sm" onClick={() => router.refresh()}>
        Tentar novamente
      </Button>
    </div>
  );
}
