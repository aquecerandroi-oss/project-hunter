"use client";

import { useAuth } from "@clerk/nextjs";

import { AnomalyTimeline } from "@/components/anomalies/anomaly-timeline";
import { CandlesChart } from "@/components/markets/candles-chart";
import { DerivativesCard } from "@/components/markets/derivatives-card";
import { formatPrice } from "@/components/markets/format";
import { OrderBook } from "@/components/markets/order-book";
import { QualityBadge } from "@/components/markets/quality-badge";
import { RecentTrades } from "@/components/markets/recent-trades";
import { computeAgeMs, formatAge, useAgeTicker } from "@/hooks/useAgeTicker";
import { useMarketChannels } from "@/hooks/useMarketChannels";
import type { Candle, MarketDetail, RtMarketMessage } from "@/lib/api/types";

export interface MarketDetailViewProps {
  detail: MarketDetail;
  candles: Candle[];
  /** Set when the candles fetch itself failed (H5) -- isolated from `detail` so a 503 on `/candles` degrades only this section, never the whole page. `null`/absent means the fetch succeeded (an empty `candles` array is then the honest "no candles yet" case `CandlesChart` already renders). */
  candlesError?: string | null;
}

/**
 * `rt:market:{exchange}:{symbol}` only carries price/bid/ask (docs/plans/M1.md
 * T1.5's realtime contract) -- book/trades below are only as fresh as the
 * page load. This makes that explicit instead of implying a live feed for
 * data that isn't one (Astra's T1.5 review).
 */
/**
 * `candidate` only counts as fresher when it exists (H4: never fall back to
 * the coalesced aggregate `ts` when `price_ts`/`book_ts` is missing) and is
 * not older than `current` -- same rule as `markets-table.tsx`'s `isFresher`,
 * duplicated here rather than shared since each file's `current` is a
 * different component's timestamp.
 */
function isFresher(current: string | null | undefined, candidate: string | null | undefined): candidate is string {
  if (!candidate) return false;
  if (!current) return true;
  const candidateTime = new Date(candidate).getTime();
  const currentTime = new Date(current).getTime();
  if (Number.isNaN(candidateTime) || Number.isNaN(currentTime)) return false;
  return candidateTime >= currentTime;
}

interface LiveHeader {
  lastPrice: string | null | undefined;
  bid: string | null | undefined;
  ask: string | null | undefined;
  components: MarketDetail["components"];
}

/**
 * H4: the price ages off `price_ts`, the book off `book_ts` -- never the
 * coalesced aggregate `tick.ts`, which a book-only update (trade feed
 * stalled) bumps just as freely as a real price change would. Each guard
 * compares against its OWN component's previous timestamp, not
 * `detail.last_update`, so a tick that only refreshes the book can't also
 * declare the price fresh.
 */
function applyLiveTick(detail: MarketDetail, tick: RtMarketMessage | undefined): LiveHeader {
  const priceIsFresh = tick !== undefined && isFresher(detail.components.ticker.ts, tick.price_ts);
  const bookIsFresh = tick !== undefined && isFresher(detail.components.book.ts, tick.book_ts);

  return {
    lastPrice: priceIsFresh ? (tick.price ?? detail.last_price) : detail.last_price,
    bid: priceIsFresh ? (tick.bid ?? detail.bid) : detail.bid,
    ask: priceIsFresh ? (tick.ask ?? detail.ask) : detail.ask,
    components: {
      ...detail.components,
      ticker: priceIsFresh
        ? { ...detail.components.ticker, ts: tick.price_ts, quality: "ok" as const }
        : detail.components.ticker,
      book: bookIsFresh ? { ...detail.components.book, ts: tick.book_ts, quality: "ok" as const } : detail.components.book,
    },
  };
}

function AsOf({ ts }: { ts: string | null | undefined }) {
  const now = useAgeTicker();
  const ageMs = computeAgeMs(ts, now);
  if (ageMs === null) return null;
  return <span className="ml-2 text-[11px] normal-case text-fg-subtle">atualizado há {formatAge(ageMs)}</span>;
}

/**
 * Book and recent trades are a snapshot fetched once with the page (T1.5b
 * joint decision #1): the realtime channel only carries price/bid/ask, so
 * animating this section on every price tick would fake activity that isn't
 * there. Every panel names its own nature and age instead of borrowing the
 * header's live quality badge -- "Snapshot · há 2 min", never implying a
 * live feed for data that isn't one.
 */
function SnapshotLabel({ ts }: { ts: string | null | undefined }) {
  const now = useAgeTicker();
  const ageMs = computeAgeMs(ts, now);
  return (
    <span className="ml-2 text-[11px] normal-case text-fg-subtle">
      Snapshot · {ageMs !== null ? `há ${formatAge(ageMs)}` : "sem dado"}
    </span>
  );
}

/** `/[orgSlug]/markets/[exchange]/[symbol]` (docs/plans/M1.md T1.5): header + candles + book + trades + derivatives, live price via `rt:market:{exchange}:{symbol}`. */
export function MarketDetailView({ detail, candles, candlesError = null }: MarketDetailViewProps) {
  const { getToken } = useAuth();
  const channel = `rt:market:${detail.exchange}:${detail.symbol}`;
  const { messages } = useMarketChannels({ channels: [channel], getAuthToken: () => getToken() });
  const tick = messages[channel] as RtMarketMessage | undefined;
  const { lastPrice, bid, ask, components } = applyLiveTick(detail, tick);

  // H3: `hot_state_ok` is the one signal for whether THIS request's Redis
  // hot-state read succeeded at all -- `book`/`recent_trades` are `null`
  // when it didn't (Redis down / WRONGTYPE), never because there is
  // genuinely no book/no trades. Both sections render that outage
  // explicitly instead of the honest-but-wrong "nothing here" empty state.
  const recentTrades = detail.recent_trades ?? null;

  return (
    <div className="flex flex-col gap-4">
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold text-fg">
          {detail.symbol} <span className="text-sm font-normal text-fg-subtle">{detail.exchange}</span>
        </h1>
        <QualityBadge
          quality={detail.data_quality}
          components={components}
          staleAfterMs={detail.stale_after_ms}
          hasOpenGap={detail.has_open_gap}
        />
        {/* 28px -- the type scale's top tier for "the big number" (docs/DESIGN.md §2), same as the KPI card anchor. */}
        <span className="font-mono text-[28px] tabular-nums text-fg">{formatPrice(lastPrice)}</span>
        <span className="text-xs text-fg-muted">
          bid {formatPrice(bid)} · ask {formatPrice(ask)}
        </span>
        <AsOf ts={components.ticker.ts} />
      </header>

      <section className="rounded-lg border border-border bg-bg-elevated p-4">
        {candlesError !== null ? (
          <p className="flex h-[360px] items-center justify-center text-sm text-fg-muted">
            Candles indisponíveis: {candlesError}
          </p>
        ) : (
          <CandlesChart candles={candles} />
        )}
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="rounded-lg border border-border bg-bg-elevated p-4">
          <h2 className="mb-2 text-xs font-medium uppercase tracking-wide text-fg-muted">
            Book
            <SnapshotLabel ts={detail.book?.ts} />
          </h2>
          <OrderBook book={detail.book ?? null} hotStateOk={detail.hot_state_ok} />
        </section>
        <section className="rounded-lg border border-border bg-bg-elevated p-4">
          <h2 className="mb-2 text-xs font-medium uppercase tracking-wide text-fg-muted">
            Trades recentes
            <SnapshotLabel ts={recentTrades?.[0]?.ts} />
          </h2>
          <RecentTrades trades={recentTrades} hotStateOk={detail.hot_state_ok} />
        </section>
      </div>

      <section className="rounded-lg border border-border bg-bg-elevated p-4">
        <h2 className="mb-2 text-xs font-medium uppercase tracking-wide text-fg-muted">Derivativos</h2>
        <DerivativesCard
          markPrice={detail.mark_price}
          openInterest={detail.open_interest}
          fundingRate={detail.funding_rate}
          fundingKind={detail.funding_kind}
          components={detail.components}
        />
      </section>

      <section className="rounded-lg border border-border bg-bg-elevated p-4">
        <h2 className="mb-2 text-xs font-medium uppercase tracking-wide text-fg-muted">Anomalias (24h)</h2>
        <AnomalyTimeline marketId={detail.id} />
      </section>
    </div>
  );
}
