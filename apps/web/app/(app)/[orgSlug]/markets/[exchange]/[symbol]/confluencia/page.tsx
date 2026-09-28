import { notFound } from "next/navigation";

import { ConfluenceView, type TimeframeLink } from "@/components/confluence/confluence-view";
import { isApiError } from "@/lib/api-error";
import { listAnomalies } from "@/lib/api/anomalies";
import type { AnomalyOut } from "@/lib/api/anomalies-types";
import { getLabSignals, listLabVersions } from "@/lib/api/lab";
import type { SignalListItemOut } from "@/lib/api/lab-types";
import { getMarketDesk } from "@/lib/api/market-desk";
import type { DeskOut } from "@/lib/api/market-desk-types";
import { getMarketEvents } from "@/lib/api/market-events";
import type { MarketEventOut } from "@/lib/api/market-events-types";
import { getCandles, getMarket } from "@/lib/api/markets";
import { resolveOrgContext } from "@/lib/api/org-context";
import { getRegimeHistory } from "@/lib/api/regime";
import type { RegimeOut } from "@/lib/api/regime-types";
import type { Candle } from "@/lib/api/types";
import { logger } from "@/lib/logger";

export interface ConfluenciaPageProps {
  params: Promise<{ orgSlug: string; exchange: string; symbol: string }>;
  searchParams: Promise<{ tf?: string; since?: string }>;
}

/** design §6: "Não é um TradingView" -- um timeframe padrão (15m) e dois alternativos (1m, 1h), e só. */
const TIMEFRAMES = ["1m", "15m", "1h"] as const;
type ConfluenceTimeframe = (typeof TIMEFRAMES)[number];
const TIMEFRAME_SECONDS: Record<ConfluenceTimeframe, number> = { "1m": 60, "15m": 900, "1h": 3600 };
const DEFAULT_TIMEFRAME: ConfluenceTimeframe = "15m";
const DEFAULT_WINDOW_HOURS = 24;
const MAX_ANOMALY_WINDOW_HOURS = 24 * 30;
/** `MAX_WINDOW` on `routers/market_desk.py` -- desk/events answer at most a 7-day span; clamped here so a wide candle window (e.g. 500 bars of 1h ≈ 21 days, Astra's review of T4.82, must-fix 8) degrades to "desk/events indisponíveis" only past 7 days back, never a blanket 422 for the whole screen. */
const MAX_DESK_EVENTS_WINDOW_MS = 7 * 24 * 3_600_000;

function parseTimeframe(raw: string | undefined): ConfluenceTimeframe {
  return (TIMEFRAMES as readonly string[]).includes(raw ?? "") ? (raw as ConfluenceTimeframe) : DEFAULT_TIMEFRAME;
}

function reasonOf(error: unknown): string {
  return isApiError(error) ? (error.detail ?? error.message) : "erro desconhecido";
}

async function loadCandles(exchange: string, symbol: string, timeframe: ConfluenceTimeframe, since: string | undefined, nowIso: string): Promise<{ candles: Candle[]; error: string | null }> {
  try {
    const candles = await getCandles(exchange, symbol, {
      timeframe,
      limit: 500,
      ...(since !== undefined ? { since, until: nowIso } : {}),
    });
    return { candles, error: null };
  } catch (error) {
    logger.error("confluence_candles_load_failed", { exchange, symbol, timeframe, error: reasonOf(error) });
    return { candles: [], error: reasonOf(error) };
  }
}

async function loadSignals(marketId: string, symbol: string, since: string, until: string): Promise<{ signals: SignalListItemOut[]; error: string | null; truncated: boolean }> {
  try {
    // Astra's review of T4.82 (must-fix 1/4): `market` (symbol) alone cannot
    // tell a spot market apart from a perpetual one (or the same symbol on
    // two exchanges) that happen to share a ticker -- 340 historical
    // spot-cohort signals are documented as still present, NEARUSDT
    // duplicated spot+perp (`.claude/state/notes-T3.73.md`). `market_id` is
    // the resolved market's own id, additive on top of `market`.
    const page = await getLabSignals({ market: symbol, market_id: marketId, state: "all", page_size: 200, emitted_from: since, emitted_to: until });
    return { signals: page.items, error: null, truncated: page.next_cursor !== null };
  } catch (error) {
    logger.error("confluence_signals_load_failed", { symbol, error: reasonOf(error) });
    return { signals: [], error: reasonOf(error), truncated: false };
  }
}

async function loadDesk(orgId: string, exchange: string, symbol: string, since: string, until: string): Promise<{ desk: DeskOut | null; error: string | null }> {
  try {
    return { desk: await getMarketDesk(orgId, exchange, symbol, { since, until }), error: null };
  } catch (error) {
    logger.error("confluence_desk_load_failed", { exchange, symbol, error: reasonOf(error) });
    return { desk: null, error: reasonOf(error) };
  }
}

async function loadEvents(orgId: string, exchange: string, symbol: string, since: string, until: string): Promise<{ events: MarketEventOut[]; error: string | null; truncated: boolean }> {
  try {
    const page = await getMarketEvents(orgId, exchange, symbol, { since, until });
    return { events: page.items, error: null, truncated: page.truncated };
  } catch (error) {
    logger.error("confluence_events_load_failed", { exchange, symbol, error: reasonOf(error) });
    return { events: [], error: reasonOf(error), truncated: false };
  }
}

async function loadRegimeHistory(): Promise<{ regimeHistory: RegimeOut[]; error: string | null }> {
  try {
    const page = await getRegimeHistory({ scope: "global", limit: 50 });
    return { regimeHistory: page.items, error: null };
  } catch (error) {
    logger.error("confluence_regime_load_failed", { error: reasonOf(error) });
    return { regimeHistory: [], error: reasonOf(error) };
  }
}

async function loadAnomalies(marketId: string, windowHours: number): Promise<{ anomalies: AnomalyOut[]; error: string | null }> {
  try {
    const page = await listAnomalies({ market_id: marketId, window_hours: Math.min(windowHours, MAX_ANOMALY_WINDOW_HOURS) });
    return { anomalies: page.items, error: null };
  } catch (error) {
    logger.error("confluence_anomalies_load_failed", { marketId, error: reasonOf(error) });
    return { anomalies: [], error: reasonOf(error) };
  }
}

async function loadStrategyVersionLabels(): Promise<Record<string, string>> {
  try {
    const { items } = await listLabVersions();
    const labels: Record<string, string> = {};
    for (const item of items) labels[item.strategy_version_id] = `${item.strategy_key} v${item.version}`;
    return labels;
  } catch (error) {
    logger.warn("confluence_versions_load_failed", { error: reasonOf(error) });
    return {};
  }
}

function buildTimeframeLinks(orgSlug: string, exchange: string, symbol: string, current: ConfluenceTimeframe, since: string | undefined): TimeframeLink[] {
  return TIMEFRAMES.map((tf) => {
    const search = new URLSearchParams();
    search.set("tf", tf);
    if (since !== undefined) search.set("since", since);
    return {
      timeframe: tf,
      href: `/${orgSlug}/markets/${encodeURIComponent(exchange)}/${encodeURIComponent(symbol)}/confluencia?${search.toString()}`,
      active: tf === current,
    };
  });
}

/**
 * `/[orgSlug]/markets/[exchange]/[symbol]/confluencia` (T4.82's design,
 * `docs/design/tela-confluencia-mercado.md`) -- candles + a signed line, a
 * news timeline and the desk's own trail on one time axis. Server Component:
 * every source is fetched in parallel, each in its own `try`/`catch` (a
 * failure in one degrades only its own lane/panel section, never the whole
 * page) -- the same isolation `MarketDetailPage` already uses for candles.
 */
export default async function ConfluenciaPage({ params, searchParams }: ConfluenciaPageProps) {
  const { orgSlug, exchange, symbol } = await params;
  const { tf, since: sinceParam } = await searchParams;
  const membership = await resolveOrgContext(orgSlug);
  if (!membership) notFound();

  const timeframe = parseTimeframe(tf);
  const timeframeSeconds = TIMEFRAME_SECONDS[timeframe];
  const now = new Date();
  const nowIso = now.toISOString();

  const market = await getMarket(exchange, symbol).catch((error: unknown) => {
    if (isApiError(error) && error.status === 404) return null;
    logger.error("confluence_market_load_failed", { exchange, symbol, error: reasonOf(error) });
    return null;
  });
  if (market === null) notFound();

  const { candles, error: candlesError } = await loadCandles(exchange, symbol, timeframe, sinceParam, nowIso);

  // The screen's own window: the loaded candles' own span when there are
  // any, else the widen request's own span, else the last 24h -- every
  // other source (signals/desk/events/anomalies) is cut to exactly this, so
  // "nada aconteceu neste período" always means the period the candles show.
  const firstCandleIso = candles[0]?.open_time;
  const effectiveSince = firstCandleIso ?? sinceParam ?? new Date(now.getTime() - DEFAULT_WINDOW_HOURS * 3_600_000).toISOString();
  const effectiveUntil = nowIso;
  const windowHours = Math.max(1, Math.ceil((now.getTime() - new Date(effectiveSince).getTime()) / 3_600_000));
  // Astra's review of T4.82 (must-fix 8): desk/events cap their own window at
  // 7 days server-side; a wide candle span (500 bars of 1h is ~21 days) must
  // not turn into a 422 for both -- clamp their own `since` independently of
  // the candles'/signals' wider one (signals allow 31 days, no clamp needed).
  const deskEventsSince = new Date(Math.max(new Date(effectiveSince).getTime(), now.getTime() - MAX_DESK_EVENTS_WINDOW_MS)).toISOString();

  const [signalsResult, deskResult, eventsResult, regimeResult, anomaliesResult, strategyVersionLabels] = await Promise.all([
    loadSignals(market.id, symbol, effectiveSince, effectiveUntil),
    loadDesk(membership.organization.id, exchange, symbol, deskEventsSince, effectiveUntil),
    loadEvents(membership.organization.id, exchange, symbol, deskEventsSince, effectiveUntil),
    loadRegimeHistory(),
    loadAnomalies(market.id, windowHours),
    loadStrategyVersionLabels(),
  ]);

  // Astra's review of T4.82 (must-fix 5): a silent row cap must not read as
  // "nada aconteceu" -- every source that can truncate says so explicitly.
  const truncationNotes: string[] = [];
  if (signalsResult.truncated) truncationNotes.push("sinais do Lab (mais de 200 nesta janela — estreite o período)");
  if (deskResult.desk?.orders_truncated === true) truncationNotes.push("ordens da mesa spot/1");
  if (deskResult.desk?.positions_truncated === true) truncationNotes.push("posições da mesa spot/1");
  if (eventsResult.truncated) truncationNotes.push("notícias");

  const search = new URLSearchParams();
  search.set("tf", timeframe);
  search.set("since", new Date(now.getTime() - DEFAULT_WINDOW_HOURS * 3_600_000).toISOString());
  const widenHref = `/${orgSlug}/markets/${encodeURIComponent(exchange)}/${encodeURIComponent(symbol)}/confluencia?${search.toString()}`;

  return (
    <ConfluenceView
      timeframeSeconds={timeframeSeconds}
      timeframeLinks={buildTimeframeLinks(orgSlug, exchange, symbol, timeframe, sinceParam)}
      widenHref={widenHref}
      candles={candles}
      candlesError={candlesError}
      signals={signalsResult.signals}
      signalsError={signalsResult.error}
      desk={deskResult.desk}
      deskError={deskResult.error}
      events={eventsResult.events}
      eventsError={eventsResult.error}
      regimeHistory={regimeResult.regimeHistory}
      regimeError={regimeResult.error}
      anomalies={anomaliesResult.anomalies}
      anomaliesError={anomaliesResult.error}
      strategyVersionLabels={strategyVersionLabels}
      truncationNotes={truncationNotes}
    />
  );
}
