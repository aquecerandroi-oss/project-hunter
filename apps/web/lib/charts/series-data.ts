import type { CandlestickData, LineData, Time, UTCTimestamp, WhitespaceData } from "lightweight-charts";

/**
 * T3.31 -- shared point sanitation for every `lightweight-charts` series in
 * the app (`candles-chart.tsx`, `portfolio-equity-chart.tsx`,
 * `lab-curve-chart.tsx`; see `.claude/state/notes-T3.31.md`). `setData`
 * itself only rejects malformed points in the *development* build --
 * `lightweight-charts.production.mjs` strips those assertions entirely
 * (dead-code-eliminated), so a non-finite value, an out-of-order time or a
 * duplicate time that dev would reject with a clear message instead reaches
 * unguarded internals in production. These helpers apply the same rules the
 * dev build already enforces, before `setData` ever sees the array, in both
 * builds.
 */

function timeAsNumber(time: Time): number {
  return time as unknown as number;
}

/** Ascending by time, last write wins on a duplicate time (`lightweight-charts` rejects both non-ascending and duplicate times unless `allowDuplicates` is set, which none of this app's charts use). */
export function sortAndDedupeByTime<T extends { time: Time }>(points: readonly T[]): T[] {
  const byTime = new Map<number, T>();
  for (const point of points) {
    const t = timeAsNumber(point.time);
    if (!Number.isFinite(t)) continue;
    byTime.set(t, point);
  }
  return Array.from(byTime.entries())
    .sort(([a], [b]) => a - b)
    .map(([, point]) => point);
}

/** A `LineData` point's own `value`; a `WhitespaceData` point (an intentional gap, no `value` key) always passes through untouched. */
function hasFiniteValue<T extends Time>(point: LineData<T> | WhitespaceData<T>): boolean {
  return !("value" in point) || Number.isFinite(point.value);
}

/** Drops non-finite `value`s (never a fabricated number for a genuinely bad point -- an honest gap in the drawn line), then sorts and dedupes by time. */
export function sanitizeLinePoints<T extends Time>(points: readonly (LineData<T> | WhitespaceData<T>)[]): (LineData<T> | WhitespaceData<T>)[] {
  return sortAndDedupeByTime(points.filter(hasFiniteValue));
}

/** Drops candles with a non-finite open/high/low/close (a partial candle is worse to show than to skip), then sorts and dedupes by time. */
export function sanitizeCandlePoints<T extends Time>(points: readonly CandlestickData<T>[]): CandlestickData<T>[] {
  const finite = points.filter((p) => [p.open, p.high, p.low, p.close].every(Number.isFinite));
  return sortAndDedupeByTime(finite);
}

/**
 * T3.31 root cause (`.claude/state/notes-T3.31.md`): `lightweight-charts`
 * shares ONE time scale across every series added to a chart. Rebuilding a
 * series' own render cache walks that shared, chart-wide list of times and
 * asks the series for its own bar at every one of them; a series with no bar
 * at a time contributed only by a *sibling* series hits an unguarded
 * `ensureNotNull` deep inside the library and throws "Error: Value is null"
 * (confirmed against the exact chunk the VPS served: `Array.map` -> a
 * per-series pane view's `Rb` -> `Sh` -> the null check). `LabCurveChart` is
 * the only chart in this app with more than one series sharing a time scale
 * (one line per strategy version, each with its own signal timestamps) --
 * every other chart has exactly one series and can never hit this.
 *
 * The fix is to never let that gap exist: every series gets an explicit
 * `WhitespaceData` point (a real gap, drawn as nothing, never interpolated)
 * at every time any *other* series in the same group uses, so the shared
 * lookup always finds a row.
 */
export function alignToUnionTimes<T extends Time>(
  seriesList: readonly (readonly (LineData<T> | WhitespaceData<T>)[])[],
): (LineData<T> | WhitespaceData<T>)[][] {
  const allTimes = new Set<number>();
  for (const points of seriesList) {
    for (const point of points) allTimes.add(timeAsNumber(point.time));
  }
  return seriesList.map((points) => {
    const byTime = new Map<number, LineData<T> | WhitespaceData<T>>();
    for (const point of points) byTime.set(timeAsNumber(point.time), point);
    for (const time of allTimes) {
      if (!byTime.has(time)) byTime.set(time, { time: time as UTCTimestamp as T });
    }
    return Array.from(byTime.entries())
      .sort(([a], [b]) => a - b)
      .map(([, point]) => point);
  });
}
