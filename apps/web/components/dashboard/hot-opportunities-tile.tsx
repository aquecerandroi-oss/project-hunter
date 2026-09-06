import Link from "next/link";

import { Button } from "@/components/ui/button";
import { isApiError } from "@/lib/api-error";
import { listRadar } from "@/lib/api/radar";
import { formatUtc } from "@/lib/format";
import { logger } from "@/lib/logger";

export type HotOpportunitiesTileLoad = { ok: true; count: number; atLeast: boolean; asOf: string } | { ok: false };

/** "Oportunidades HOT" (brief line 12) -- `status=HOT` count from the same global radar contract `/radar` reads, never a locally-derived guess. */
export async function loadHotOpportunitiesTile(): Promise<HotOpportunitiesTileLoad> {
  try {
    const page = await listRadar({ status: ["HOT"], limit: 200 });
    return { ok: true, count: page.items.length, atLeast: page.next_cursor !== null, asOf: page.as_of };
  } catch (error) {
    const reason = isApiError(error) ? (error.detail ?? error.message) : "erro desconhecido";
    logger.error("dashboard_hot_opportunities_tile_failed", { error: reason });
    return { ok: false };
  }
}

export function HotOpportunitiesTile({ orgSlug, result }: { orgSlug: string; result: HotOpportunitiesTileLoad }) {
  return (
    <section className="rounded-lg border border-border bg-bg-elevated p-4 transition-colors hover:border-border-strong">
      <h2 className="text-xs font-medium uppercase tracking-wide text-fg-muted">Oportunidades HOT</h2>
      {!result.ok ? (
        <p className="mt-1 text-sm text-fg-muted">sem verificação</p>
      ) : (
        <>
          <p className="num mt-1 text-[28px] font-semibold text-fg">{result.atLeast ? `${result.count}+` : result.count}</p>
          <p className="mt-1 text-[11px] text-fg-subtle">verificado {formatUtc(result.asOf)}</p>
        </>
      )}
      <Button asChild variant="outline" size="sm" className="mt-3">
        <Link href={`/${orgSlug}/radar?status=HOT`}>Ver no radar</Link>
      </Button>
    </section>
  );
}
