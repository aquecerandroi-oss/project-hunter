import { notFound } from "next/navigation";

import { AutoRefresh } from "@/components/auto-refresh";
import { DEFAULT_AUTO_REFRESH_INTERVAL_MS, autoRefreshIntervalMs } from "@/lib/auto-refresh-interval";
import { MarketsError } from "@/components/markets/markets-error";
import { MarketsTable } from "@/components/markets/markets-table";
import { isApiError } from "@/lib/api-error";
import { listMarkets } from "@/lib/api/markets";
import { resolveOrgContext } from "@/lib/api/org-context";
import type { MarketRow, MarketsSummary } from "@/lib/api/types";
import { logger } from "@/lib/logger";

export interface MarketsPageProps {
  params: Promise<{ orgSlug: string }>;
}

// The M1 universe defaults to the top 200 monitored perpetuals by volume
// (docs/plans/M1.md's "Decisões deste plano") -- one request covers it, and
// it doubles as the virtualization/realtime-channel budget the table uses.
const MARKETS_PAGE_LIMIT = 200;

type MarketsLoad =
  | { ok: true; items: MarketRow[]; summary: MarketsSummary; truncated: boolean; staleAfterMs: number }
  | { ok: false; reason: string };

/**
 * Fetches, never constructs JSX -- `react-hooks/error-boundaries` (part of
 * this repo's `eslint-plugin-react-hooks` recommended config) flags JSX
 * built inside a try/catch because React doesn't render synchronously, so
 * the catch would never actually see a rendering error. Splitting fetch from
 * render keeps the try/catch doing only what it can actually catch.
 */
async function loadMarkets(): Promise<MarketsLoad> {
  try {
    const { items, summary, next_cursor, stale_after_ms } = await listMarkets({
      monitored: true,
      limit: MARKETS_PAGE_LIMIT,
    });
    // `next_cursor` non-null means the monitored universe grew past
    // `MARKETS_PAGE_LIMIT` -- the search box below only ever sees `items`,
    // so a market that exists but sits on page 2 would otherwise read as a
    // false negative ("Nenhum mercado encontrado") instead of the truth
    // (T1.5 review F6).
    return { ok: true, items, summary, truncated: next_cursor !== null, staleAfterMs: stale_after_ms };
  } catch (error) {
    const reason = isApiError(error) ? (error.detail ?? error.message) : "erro desconhecido";
    logger.error("markets_page_load_failed", { error: reason });
    return { ok: false, reason };
  }
}

/** `/[orgSlug]/markets` (docs/PRODUCT.md §4, available from M1) -- the monitored Binance universe, real prices, honest staleness. */
export default async function MarketsPage({ params }: MarketsPageProps) {
  const { orgSlug } = await params;
  const membership = await resolveOrgContext(orgSlug);
  if (!membership) notFound();

  const result = await loadMarkets();
  // H9: paced off this response's own `stale_after_ms` when we have one; the
  // fixed default only applies to the (rare, already-erroring) case where
  // the fetch itself failed and there is no threshold to pace against.
  const intervalMs = result.ok ? autoRefreshIntervalMs(result.staleAfterMs) : DEFAULT_AUTO_REFRESH_INTERVAL_MS;
  return (
    <div className="flex flex-col gap-4">
      <AutoRefresh intervalMs={intervalMs} />
      <h1 className="text-xl font-semibold text-fg">Markets</h1>
      {result.ok ? (
        <MarketsTable
          orgSlug={orgSlug}
          items={result.items}
          summary={result.summary}
          staleAfterMs={result.staleAfterMs}
          truncated={result.truncated}
        />
      ) : (
        <MarketsError reason={result.reason} />
      )}
    </div>
  );
}
