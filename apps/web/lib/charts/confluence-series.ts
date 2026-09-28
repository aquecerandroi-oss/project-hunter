import type { UTCTimestamp } from "lightweight-charts";

import type { Candle } from "@/lib/api/types";
import { sanitizeCandlePoints } from "@/lib/charts/series-data";

/** Ascending, deduped bar-open times (whole seconds) -- the one series every confluence overlay (chart, lanes, cursor keyboard nav) shares, so none of them can disagree about which instant a given index means. */
export function confluenceCandleTimes(candles: readonly Candle[]): UTCTimestamp[] {
  const raw = candles.map((candle) => ({
    time: Math.floor(new Date(candle.open_time).getTime() / 1000) as UTCTimestamp,
    open: Number(candle.open),
    high: Number(candle.high),
    low: Number(candle.low),
    close: Number(candle.close),
  }));
  return sanitizeCandlePoints(raw).map((c) => c.time as UTCTimestamp);
}

/**
 * The confluence screen's own bar lookup (design §3, "regra de cobertura"):
 * the bar whose open is `<= target` and whose close (`open + timeframeS`) is
 * `> target` -- a floor, never `lab-trendline-series.ts`'s `nearestCandleIndex`
 * with its 1.5-bar tolerance. An instant 20 minutes past the last loaded 15m
 * candle must read as "fora dos candles carregados", never silently snap to
 * the last bar the way the tolerance-based lookup would.
 *
 * `times` must already be ascending and deduped (every candle series in this
 * app is built through `sanitizeCandlePoints`, which guarantees both).
 */
export function barIndexContaining(
  times: readonly UTCTimestamp[],
  targetIso: string,
  timeframeS: number,
): number | null {
  const targetMs = new Date(targetIso).getTime();
  if (!Number.isFinite(targetMs) || times.length === 0) return null;
  const targetS = Math.floor(targetMs / 1000);
  const first = times[0];
  if (first === undefined || targetS < first) return null;

  // Binary search for the largest index whose open time is <= targetS.
  let lo = 0;
  let hi = times.length - 1;
  while (lo < hi) {
    const mid = Math.ceil((lo + hi) / 2);
    const midTime = times[mid] as UTCTimestamp;
    if (midTime <= targetS) lo = mid;
    else hi = mid - 1;
  }
  const candidateOpen = times[lo] as UTCTimestamp;
  return targetS < candidateOpen + timeframeS ? lo : null;
}
