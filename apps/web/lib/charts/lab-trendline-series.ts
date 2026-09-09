import type { CandlestickData, LineData, Time, UTCTimestamp, WhitespaceData } from "lightweight-charts";

import type { Candle } from "@/lib/api/types";
import { sanitizeCandlePoints } from "@/lib/charts/series-data";
import { asOfFromPatternBars, lineTimeMsForIdx, linePriceAtTimeMs, type TrendlineGeometry } from "@/lib/lab-trendline";

/**
 * Chart-data shaping for the trend-line overlay (brief T3.49), split out of
 * `components/lab/lab-trendline-overlay.tsx` so the tricky index/segment
 * math is Vitest-able without mocking `lightweight-charts`' runtime (only
 * its types are used here, which cost nothing at test time).
 *
 * T3.31 root cause (`.claude/state/notes-T3.31.md`): `lightweight-charts`
 * shares ONE time scale across every series on a chart; a series missing a
 * point at a time a *sibling* series uses crashes with "Error: Value is
 * null". Every overlay line built here is produced by mapping over the
 * *exact same* `times` array the candlestick series was built from
 * (`buildRangeLine`), so every series on this chart always has a point --
 * `value` inside its own range, `WhitespaceData` (an honest gap) everywhere
 * else -- at every one of the candlestick series' own timestamps. There is
 * no separate `alignToUnionTimes` call because there is only one real
 * source of times to begin with.
 */

const TIMEFRAME_MINUTES = 15;
/** A candidate match further than this from its target is treated as "not covered by the fetched candles" rather than silently snapped to an unrelated bar. */
const NEAREST_TOLERANCE_MS = TIMEFRAME_MINUTES * 60_000 * 1.5;

function toUnix(iso: string): UTCTimestamp {
  return Math.floor(new Date(iso).getTime() / 1000) as UTCTimestamp;
}

export function toCandleSeries(candles: Candle[]): CandlestickData<Time>[] {
  const raw = candles.map((c) => ({
    time: toUnix(c.open_time),
    open: Number(c.open),
    high: Number(c.high),
    low: Number(c.low),
    close: Number(c.close),
  }));
  return sanitizeCandlePoints(raw);
}

const BUCKET_MS = TIMEFRAME_MINUTES * 60_000;

function bucketStartMs(iso: string): number {
  return Math.floor(new Date(iso).getTime() / BUCKET_MS) * BUCKET_MS;
}

/**
 * Real 15m OHLCV, aggregated from real 1m final candles -- T3.49 found that
 * `candles.timeframe = '15m'` has zero rows anywhere in this system (dev and
 * the VPS both only ever materialize `1m`; `hunter_strategy_worker.replay.engine`
 * itself resamples 1m -> 15m in memory for every strategy evaluation, the
 * same rule applied here). Every bucket's OHLCV comes straight from the 1m
 * candles inside it -- open of the first, high/low of the extremes, close of
 * the last, volume summed; never an invented price. A bucket at either edge
 * of the fetched page can be partial (fewer than 15 real minutes) -- the
 * overlay's own `nearestCandleIndex` tolerance already treats an
 * insufficiently-covered instant as "not covered", never fabricating past
 * it. `apps/web/lib/api/lab-actions.ts::loadLabTrendlineCandlesAction` is
 * the only caller (server-only, since it also does the `getCandles` fetch).
 */
const MINUTES_PER_BUCKET = 15;

export function aggregateTo15m(candles1m: readonly Candle[]): Candle[] {
  const buckets = new Map<number, Candle[]>();
  for (const candle of candles1m) {
    const start = bucketStartMs(candle.open_time);
    const group = buckets.get(start);
    if (group) group.push(candle);
    else buckets.set(start, [candle]);
  }
  const starts = Array.from(buckets.keys()).sort((a, b) => a - b);
  const out: Candle[] = [];
  for (const start of starts) {
    const group = (buckets.get(start) ?? []).slice().sort((a, b) => new Date(a.open_time).getTime() - new Date(b.open_time).getTime());
    const first = group[0];
    const last = group[group.length - 1];
    if (!first || !last) continue;
    // Same completeness rule as the server-side export of T3.50
    // (`having count(*) = 15`): a bucket missing any 1m candle is not a 15m
    // candle, it is a partial minute range shown as if it were fifteen --
    // dropped, never emitted (review of T3.49).
    if (group.length < MINUTES_PER_BUCKET) continue;
    const volume = group.reduce((sum, c) => sum + Number(c.volume), 0);
    out.push({
      open_time: new Date(start).toISOString(),
      close_time: new Date(start + BUCKET_MS).toISOString(),
      open: first.open,
      high: String(Math.max(...group.map((c) => Number(c.high)))),
      low: String(Math.min(...group.map((c) => Number(c.low)))),
      close: last.close,
      volume: String(volume),
    } as Candle);
  }
  return out;
}

export function candleTimes(series: readonly CandlestickData<Time>[]): UTCTimestamp[] {
  return series.map((c) => c.time as UTCTimestamp);
}

/** Index of the candle time closest to `targetMs`, or `null` when the series is empty or the closest candle is still more than 1.5 bars away. */
export function nearestCandleIndex(times: readonly UTCTimestamp[], targetMs: number): number | null {
  const first = times[0];
  if (first === undefined) return null;
  const targetS = Math.floor(targetMs / 1000);
  let best = 0;
  let bestDiff = Math.abs(first - targetS);
  for (let i = 1; i < times.length; i++) {
    // `i < times.length` guarantees a defined element -- `noUncheckedIndexedAccess` cannot see that from the loop bound alone.
    const diff = Math.abs((times[i] as UTCTimestamp) - targetS);
    if (diff < bestDiff) {
      best = i;
      bestDiff = diff;
    }
  }
  return bestDiff * 1000 <= NEAREST_TOLERANCE_MS ? best : null;
}

/** A segment drawn only across `times[lo..hi]`, `WhitespaceData` (a real gap, never interpolated) everywhere else on the shared scale. */
export function buildRangeLine(
  times: readonly UTCTimestamp[],
  startIdx: number,
  endIdx: number,
  priceAt: (index: number) => number,
): (LineData<Time> | WhitespaceData<Time>)[] {
  const lo = Math.min(startIdx, endIdx);
  const hi = Math.max(startIdx, endIdx);
  return times.map((time, index) => (index >= lo && index <= hi ? { time, value: priceAt(index) } : { time }));
}

export interface TrendlineLineSegments {
  /** Solid, from `line_first_idx` to the decision bar -- `null` when the fetched candles do not cover that range. */
  used: (LineData<Time> | WhitespaceData<Time>)[] | null;
  /** Dashed, from the decision bar to the exit bar -- `null` when there is no exit yet, or it falls outside the fetched candles. */
  extension: (LineData<Time> | WhitespaceData<Time>)[] | null;
  /** Portuguese reasons for whichever of the two above is `null` (brief: never fabricate, say what is missing). */
  notes: string[];
  /** Index of the decision bar on `times`, when found -- reused by the caller to place the pivot marker relative to it; `null` otherwise. */
  decisionIdx: number | null;
}

/** The used-line solid segment plus its dashed extension to the exit (brief item 1a). */
export function buildUsedLineSegments(
  times: readonly UTCTimestamp[],
  geometry: TrendlineGeometry,
  decisionBarCloseIso: string,
  exitTsIso: string | null,
): TrendlineLineSegments {
  const notes: string[] = [];
  if (geometry.patternBars === null || geometry.firstIdx === null || geometry.priceAtDecision === null || geometry.slopePerBar === null) {
    return { used: null, extension: null, decisionIdx: null, notes: ["geometria da linha incompleta -- linha não desenhada"] };
  }
  const asOf = asOfFromPatternBars(geometry.patternBars);
  const line = { priceAtDecision: geometry.priceAtDecision, slopePerBar: geometry.slopePerBar };
  // `priceAt` is only ever called with an index inside `times` (`buildRangeLine` maps over `times` itself) -- `noUncheckedIndexedAccess` cannot see that through the closure.
  const priceAt = (index: number): number => linePriceAtTimeMs(line, decisionBarCloseIso, (times[index] as UTCTimestamp) * 1000, TIMEFRAME_MINUTES);

  const firstMs = lineTimeMsForIdx(decisionBarCloseIso, asOf, geometry.firstIdx, TIMEFRAME_MINUTES);
  const decisionMs = new Date(decisionBarCloseIso).getTime();
  const startIdx = nearestCandleIndex(times, firstMs);
  const decisionIdx = nearestCandleIndex(times, decisionMs);

  const used = startIdx !== null && decisionIdx !== null ? buildRangeLine(times, startIdx, decisionIdx, priceAt) : null;
  if (used === null) notes.push("candles reais não cobrem o início da linha -- trecho sólido não desenhado");

  let extension: TrendlineLineSegments["extension"] = null;
  if (!exitTsIso) {
    notes.push("operação sem saída registrada -- extensão pontilhada não desenhada");
  } else if (decisionIdx === null) {
    notes.push("decisão fora das candles carregadas -- extensão pontilhada não desenhada");
  } else {
    const exitIdx = nearestCandleIndex(times, new Date(exitTsIso).getTime());
    if (exitIdx !== null && exitIdx > decisionIdx) extension = buildRangeLine(times, decisionIdx, exitIdx, priceAt);
    else notes.push("candles reais não cobrem a saída -- extensão pontilhada não desenhada");
  }

  return { used, extension, decisionIdx, notes };
}

export interface HorizontalLevel {
  label: string;
  price: string | null;
}

export interface HorizontalSegment {
  label: string;
  points: (LineData<Time> | WhitespaceData<Time>)[];
}

interface HorizontalRange {
  startIdx: number | null;
  endIdx: number | null;
  note: string | null;
}

/** The [entry, exit] index range every level segment shares -- split out of `buildHorizontalSegments` purely to stay under the statement-count lint budget. */
function resolveHorizontalRange(times: readonly UTCTimestamp[], entryTsIso: string | null, exitTsIso: string | null): HorizontalRange {
  if (!entryTsIso) return { startIdx: null, endIdx: null, note: "sem entrada registrada -- entrada/stop/alvo não desenhados" };
  const startIdx = nearestCandleIndex(times, new Date(entryTsIso).getTime());
  if (startIdx === null) return { startIdx: null, endIdx: null, note: "candles reais não cobrem a entrada -- entrada/stop/alvo não desenhados" };
  const lastTime = times.length > 0 ? (times[times.length - 1] as UTCTimestamp) : null;
  const endMs = exitTsIso ? new Date(exitTsIso).getTime() : lastTime !== null ? lastTime * 1000 : null;
  const endIdx = endMs === null ? null : (nearestCandleIndex(times, endMs) ?? times.length - 1);
  if (endIdx === null) return { startIdx, endIdx: null, note: "sem candle final para desenhar entrada/stop/alvo" };
  return { startIdx, endIdx, note: null };
}

/** Entry/stop/target as bounded horizontal segments from entry time to exit time (brief item 1c) -- never the full chart width. */
export function buildHorizontalSegments(
  times: readonly UTCTimestamp[],
  entryTsIso: string | null,
  exitTsIso: string | null,
  levels: readonly HorizontalLevel[],
): { segments: HorizontalSegment[]; notes: string[] } {
  const notes: string[] = [];
  const range = resolveHorizontalRange(times, entryTsIso, exitTsIso);
  if (range.note !== null) notes.push(range.note);
  if (range.startIdx === null || range.endIdx === null) return { segments: [], notes };
  const startIdx = range.startIdx;
  const endIdx = range.endIdx;
  const segments: HorizontalSegment[] = [];
  for (const level of levels) {
    if (level.price === null) {
      notes.push(`sem ${level.label.toLowerCase()} registrado`);
      continue;
    }
    const price = Number(level.price);
    if (!Number.isFinite(price)) continue;
    segments.push({ label: level.label, points: buildRangeLine(times, startIdx, endIdx, () => price) });
  }
  return { segments, notes };
}

/** Index nearest an ISO timestamp, or `null` when either is absent/uncovered -- the exit marker's own lookup. */
export function markerIndexNear(times: readonly UTCTimestamp[], iso: string | null): number | null {
  if (!iso) return null;
  return nearestCandleIndex(times, new Date(iso).getTime());
}

/** `pivot_low_idx` converted to a candle index via the same `idx -> bar time` rule as the line itself (`lineTimeMsForIdx`) -- `null` when either field is absent or the pivot's own bar falls outside the fetched candles. */
export function pivotBarIndex(times: readonly UTCTimestamp[], geometry: Pick<TrendlineGeometry, "pivotLowIdx" | "patternBars">, decisionBarCloseIso: string): number | null {
  if (geometry.pivotLowIdx === null || geometry.patternBars === null) return null;
  const asOf = asOfFromPatternBars(geometry.patternBars);
  const pivotMs = lineTimeMsForIdx(decisionBarCloseIso, asOf, geometry.pivotLowIdx, TIMEFRAME_MINUTES);
  return nearestCandleIndex(times, pivotMs);
}
