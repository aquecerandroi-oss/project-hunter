import { notFound } from "next/navigation";

import { AutoRefresh } from "@/components/auto-refresh";
import { autoRefreshIntervalMs } from "@/lib/auto-refresh-interval";
import { MarketDetailView } from "@/components/markets/market-detail-view";
import { MarketsError } from "@/components/markets/markets-error";
import { isApiError } from "@/lib/api-error";
import { getCandles, getMarket } from "@/lib/api/markets";
import { resolveOrgContext } from "@/lib/api/org-context";
import type { Candle, MarketDetail } from "@/lib/api/types";
import { logger } from "@/lib/logger";

export interface MarketDetailPageProps {
  params: Promise<{ orgSlug: string; exchange: string; symbol: string }>;
}

const CANDLES_TIMEFRAME = "1m";
const CANDLES_LIMIT = 500;

type DetailLoad =
  | { ok: true; detail: MarketDetail }
  | { ok: false; notFound: true }
  | { ok: false; notFound: false; reason: string };

type CandlesLoad = { ok: true; candles: Candle[] } | { ok: false; reason: string };

/**
 * H5: isolated from `loadCandles` below -- these used to share one
 * `Promise.all`/`try` in `loadDetail`, so a 503 on `/candles` alone wiped out
 * price, book, trades AND derivatives too (candles are the least reliable of
 * the two: same read path as a heavier date-range query, more likely to time
 * out). Fetches only -- see `markets/page.tsx`'s `loadMarkets` docstring on
 * why JSX never gets built inside this try/catch.
 */
async function loadDetail(exchange: string, symbol: string): Promise<DetailLoad> {
  try {
    const detail = await getMarket(exchange, symbol);
    return { ok: true, detail };
  } catch (error) {
    if (isApiError(error) && error.status === 404) return { ok: false, notFound: true };
    const reason = isApiError(error) ? (error.detail ?? error.message) : "erro desconhecido";
    logger.error("market_detail_load_failed", { exchange, symbol, error: reason });
    return { ok: false, notFound: false, reason };
  }
}

/** H5: its own isolated fetch/catch -- a candles failure degrades only `CandlesChart`'s section (`MarketDetailView`'s `candlesError` prop), never the rest of the page. */
async function loadCandles(exchange: string, symbol: string): Promise<CandlesLoad> {
  try {
    const candles = await getCandles(exchange, symbol, { timeframe: CANDLES_TIMEFRAME, limit: CANDLES_LIMIT });
    return { ok: true, candles };
  } catch (error) {
    const reason = isApiError(error) ? (error.detail ?? error.message) : "erro desconhecido";
    logger.error("market_candles_load_failed", { exchange, symbol, error: reason });
    return { ok: false, reason };
  }
}

/** `/[orgSlug]/markets/[exchange]/[symbol]` (docs/plans/M1.md T1.5) -- a pair that doesn't exist reads as 404, never an error page. */
export default async function MarketDetailPage({ params }: MarketDetailPageProps) {
  const { orgSlug, exchange, symbol } = await params;
  const membership = await resolveOrgContext(orgSlug);
  if (!membership) notFound();

  const [detailResult, candlesResult] = await Promise.all([loadDetail(exchange, symbol), loadCandles(exchange, symbol)]);
  if (!detailResult.ok && detailResult.notFound) notFound();

  if (!detailResult.ok) {
    // H5: `AutoRefresh` stays mounted even on this honest failure state --
    // it used to sit only in the success branch below, so one transient
    // fetch failure permanently stopped the page's own automatic retry (the
    // user's only path back to a working page was a manual reload).
    return (
      <>
        <AutoRefresh />
        <MarketsError reason={detailResult.reason} />
      </>
    );
  }

  return (
    <>
      <AutoRefresh intervalMs={autoRefreshIntervalMs(detailResult.detail.stale_after_ms)} />
      <MarketDetailView
        detail={detailResult.detail}
        candles={candlesResult.ok ? candlesResult.candles : []}
        candlesError={candlesResult.ok ? null : candlesResult.reason}
      />
    </>
  );
}
