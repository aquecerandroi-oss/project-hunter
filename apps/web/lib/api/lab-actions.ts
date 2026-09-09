"use server";

import { isApiError } from "@/lib/api-error";
import { getLabCurve, getLabSignals, type LabCurveParams } from "@/lib/api/lab";
import { getCandles, listMarkets } from "@/lib/api/markets";
import type { Candle } from "@/lib/api/types";
import { aggregateTo15m } from "@/lib/charts/lab-trendline-series";
import { getServerSession } from "@/lib/server/auth";

import type { CurveOut } from "./lab-types";

export interface LabCurveActionOutcome {
  ok: boolean;
  curve: CurveOut | null;
  reason?: string;
}

/**
 * Server Action behind `lab-curve-section.tsx`'s "Coorte da curva" selector
 * (brief T3.24b addendum A3): `lib/api/lab.ts` is `"server-only"`, so the
 * client cannot call `getLabCurve` directly for the on-demand "replay"
 * overlay -- same boundary `loadLabSignalEnvelopeAction` below also crosses.
 */
export async function loadLabCurveAction(params: LabCurveParams): Promise<LabCurveActionOutcome> {
  const session = await getServerSession();
  if (!session) return { ok: false, curve: null, reason: "unauthenticated" };

  try {
    const curve = await getLabCurve(params);
    return { ok: true, curve };
  } catch (error) {
    const reason = isApiError(error) ? (error.detail ?? error.message) : "erro desconhecido";
    return { ok: false, curve: null, reason };
  }
}

export interface LabEnvelopeActionOutcome {
  ok: boolean;
  envelope: Record<string, unknown> | null;
  reason?: string;
}

/**
 * Fetches one signal's full envelope on demand (`?include=envelope`,
 * SHADOW-LAB.md §2's immutable `supporting_features`) -- the list endpoint
 * omits it by default because it can be large and is redundant for most of
 * the table's uses (contract-S3-lab.md). Re-queries by the same filters plus
 * `strategy_version_id`+cursor is not available per-signal, so this instead
 * asks for a single-item page filtered down to just that signal's market and
 * scans for the matching id -- the API has no `GET /signals/{id}`, and this
 * brief's allowed files do not include adding one.
 */
export async function loadLabSignalEnvelopeAction(
  signalId: string,
  market: string,
  strategyVersionId: string,
  cohort: string,
): Promise<LabEnvelopeActionOutcome> {
  const session = await getServerSession();
  if (!session) return { ok: false, envelope: null, reason: "unauthenticated" };

  try {
    const page = await getLabSignals({
      market,
      strategy_version_id: strategyVersionId,
      cohort,
      include: ["envelope"],
      page_size: 200,
    });
    const match = page.items.find((item) => item.signal_id === signalId);
    if (!match) return { ok: false, envelope: null, reason: "sinal não encontrado nesta página" };
    return { ok: true, envelope: match.supporting_features };
  } catch (error) {
    const reason = isApiError(error) ? (error.detail ?? error.message) : "erro desconhecido";
    return { ok: false, envelope: null, reason };
  }
}

export interface LabTrendlineCandlesOutcome {
  ok: boolean;
  candles: Candle[];
  /** `true` when `candles` came from aggregating real 1m final candles rather than native 15m rows -- see the long comment below. Only meaningful when `ok`. */
  derived: boolean;
  reason?: string;
}

/** `MAX_CANDLES_LIMIT` in `apps/api/hunter_api/routers/markets.py` -- the API caps `limit` regardless of timeframe. */
const MAX_CANDLES_LIMIT = 1500;

/**
 * 15m candles for the trend-line overlay (brief T3.49): `SignalListItemOut.market`
 * is a bare symbol (same gap `resolveMarketHrefAction` below already works
 * around), so this first resolves the real exchange via `listMarkets({ q })`,
 * then reads a real historical window (`getCandles(..., { before, limit })`,
 * `lib/api/markets.ts` -- both `server-only`, hence the boundary) around the
 * operation's own decision/exit instants (`lib/lab-trendline.ts`'s
 * `computeCandleWindow` computed `beforeIso`/`limit`). Zero or several
 * exchange matches is an honest failure, never a guess.
 *
 * T3.49 finding: `candles.timeframe = '15m'` has zero rows in this system,
 * dev or the VPS (checked both, read-only) -- nothing ever materializes it;
 * `hunter_strategy_worker.replay.engine` resamples `1m` in memory for every
 * strategy evaluation instead. So the native 15m fetch below is tried first
 * (in case a future aggregator ever fills it), and falls back to fetching
 * real 1m final candles over the same window and aggregating them
 * (`aggregateTo15m`) -- real OHLCV, never invented, flagged `derived: true`
 * so the caller can say so on screen. A window wider than
 * `MAX_CANDLES_LIMIT` minutes is truncated from its oldest end (the API's
 * own `before`+`limit` pagination already works this way); the overlay's own
 * per-element coverage check already renders "not covered" honestly rather
 * than fabricate past a truncated page.
 */
export async function loadLabTrendlineCandlesAction(market: string, beforeIso: string, limit: number): Promise<LabTrendlineCandlesOutcome> {
  const session = await getServerSession();
  if (!session) return { ok: false, candles: [], derived: false, reason: "unauthenticated" };

  try {
    const page = await listMarkets({ q: market, limit: 10 });
    const exact = page.items.filter((item) => item.symbol === market);
    const match = exact.length === 1 ? exact[0] : undefined;
    if (!match) return { ok: false, candles: [], derived: false, reason: "mercado ambíguo ou não encontrado" };

    const native = await getCandles(match.exchange, match.symbol, { timeframe: "15m", before: beforeIso, limit });
    if (native.length > 0) return { ok: true, candles: native, derived: false };

    const oneMinuteLimit = Math.min(limit * 15, MAX_CANDLES_LIMIT);
    const oneMinute = await getCandles(match.exchange, match.symbol, { timeframe: "1m", before: beforeIso, limit: oneMinuteLimit });
    return { ok: true, candles: aggregateTo15m(oneMinute), derived: true };
  } catch (error) {
    const reason = isApiError(error) ? (error.detail ?? error.message) : "erro desconhecido";
    return { ok: false, candles: [], derived: false, reason };
  }
}

/**
 * `SignalListItemOut.market` is a bare symbol (`Market.symbol`, no exchange
 * -- `repositories/lab_signals.py`'s query never selects `Market.exchange`),
 * so this page cannot build a `/markets/[exchange]/[symbol]` link from the
 * signals response alone without guessing the exchange, which risks
 * pointing at the wrong row if the same symbol is ever listed on more than
 * one exchange (CLAUDE.md: no invented data). This resolves the real
 * exchange via the already-implemented, already-tested `listMarkets({ q })`
 * (`lib/api/markets.ts`, T1.4) -- exactly one match routes straight to the
 * market detail page; anything else (zero or several matches) falls back to
 * the markets search results, which is still a real, honest page.
 */
export async function resolveMarketHrefAction(orgSlug: string, symbol: string): Promise<string> {
  const searchFallback = `/${orgSlug}/markets?q=${encodeURIComponent(symbol)}`;
  const session = await getServerSession();
  if (!session) return searchFallback;

  try {
    // No `monitored` filter: a market the Shadow Lab evaluated may no longer
    // be in the currently-monitored universe, and `monitored: false` would
    // wrongly exclude a market that still IS monitored (`Market.is_monitored
    // .is_(monitored)` in `repositories/markets.py` filters both ways).
    const page = await listMarkets({ q: symbol, limit: 10 });
    const exact = page.items.filter((item) => item.symbol === symbol);
    const match = exact.length === 1 ? exact[0] : undefined;
    if (!match) return searchFallback;
    return `/${orgSlug}/markets/${encodeURIComponent(match.exchange)}/${encodeURIComponent(match.symbol)}`;
  } catch {
    return searchFallback;
  }
}
