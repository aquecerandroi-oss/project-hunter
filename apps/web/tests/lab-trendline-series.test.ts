import type { UTCTimestamp } from "lightweight-charts";
import { describe, expect, it } from "vitest";

import {
  aggregateTo15m,
  buildHorizontalSegments,
  buildRangeLine,
  buildUsedLineSegments,
  candleTimes,
  markerIndexNear,
  nearestCandleIndex,
  pivotBarIndex,
  toCandleSeries,
} from "@/lib/charts/lab-trendline-series";
import type { TrendlineGeometry } from "@/lib/lab-trendline";
import type { Candle } from "@/lib/api/types";

// Narrow instead of `!` (no-non-null-assertion): fail with a clear message
// rather than assert past a genuinely `null`/missing result.
function mustExist<T>(value: T | null | undefined, what: string): T {
  if (value === null || value === undefined) throw new Error(`expected ${what} to be present`);
  return value;
}

/** 5 candles, 15m apart, starting at `2026-08-19T23:00:00Z` (the decision bar's own close is candle index 3, `23:45:00Z`). */
function makeCandles(): Candle[] {
  const start = new Date("2026-08-19T23:00:00Z").getTime();
  return Array.from({ length: 5 }, (_, i) => ({
    open_time: new Date(start + i * 15 * 60_000).toISOString(),
    close_time: new Date(start + (i + 1) * 15 * 60_000).toISOString(),
    open: "1",
    high: "1",
    low: "1",
    close: "1",
    volume: "1",
  })) as Candle[];
}

function baseGeometry(overrides: Partial<TrendlineGeometry> = {}): TrendlineGeometry {
  return {
    lineKind: "support",
    lineId: "abc123",
    slopePerBar: 1,
    touches: 3,
    violations: 0,
    firstIdx: 92, // -> 23:00:00Z, candle index 0
    lastIdx: 95,
    validFromIdx: 95,
    priceAtDecision: 100,
    eventKind: "bounce",
    eventDistanceAtr: 0.5,
    pivotLowPrice: 90,
    pivotLowIdx: 93, // -> 23:15:00Z, candle index 1
    patternBars: 96, // as_of = 95 -> 23:45:00Z, candle index 3
    patternPivots: 10,
    patternLines: 2,
    patternRetiredLines: 0,
    channelWidthAtr: null,
    channelAvailable: false,
    patternParams: null,
    patternParamsRaw: null,
    ...overrides,
  };
}

describe("toCandleSeries / candleTimes / nearestCandleIndex", () => {
  it("converts candles to a sorted time array and finds the closest index within tolerance", () => {
    const series = toCandleSeries(makeCandles());
    const times = candleTimes(series);
    expect(times).toHaveLength(5);
    expect(nearestCandleIndex(times, new Date("2026-08-19T23:45:00Z").getTime())).toBe(3);
    // 5 minutes off is still well inside 1.5 bars (22.5 min).
    expect(nearestCandleIndex(times, new Date("2026-08-19T23:50:00Z").getTime())).toBe(3);
  });

  it("returns null when the closest candle is more than 1.5 bars away", () => {
    const series = toCandleSeries(makeCandles());
    const times = candleTimes(series);
    expect(nearestCandleIndex(times, new Date("2026-08-20T04:00:00Z").getTime())).toBeNull();
  });

  it("returns null for an empty series", () => {
    expect(nearestCandleIndex([], 0)).toBeNull();
  });
});

describe("buildRangeLine: a value only inside [lo, hi], WhitespaceData everywhere else", () => {
  it("marks every other point as a real gap, never interpolated or fabricated", () => {
    const times = [0, 900, 1800, 2700, 3600] as UTCTimestamp[];
    const line = buildRangeLine(times, 1, 3, (i) => i * 10);
    expect(line).toEqual([{ time: 0 }, { time: 900, value: 10 }, { time: 1800, value: 20 }, { time: 2700, value: 30 }, { time: 3600 }]);
  });

  it("accepts reversed start/end indices the same way", () => {
    const times = [0, 900, 1800] as UTCTimestamp[];
    expect(buildRangeLine(times, 2, 0, (i) => i)).toEqual([{ time: 0, value: 0 }, { time: 900, value: 1 }, { time: 1800, value: 2 }]);
  });
});

describe("buildUsedLineSegments: the solid segment to the decision bar, dashed extension to the exit", () => {
  it("draws both segments when candles cover first_idx, the decision bar and the exit", () => {
    const series = toCandleSeries(makeCandles());
    const times = candleTimes(series);
    const result = buildUsedLineSegments(times, baseGeometry(), "2026-08-19T23:45:00Z", "2026-08-20T00:15:00Z");
    expect(result.notes).toEqual([]);
    expect(result.decisionIdx).toBe(3);
    // Solid segment: index 0 (first_idx) through 3 (decision) carry a value.
    expect(mustExist(result.used, "used segment").filter((p) => "value" in p)).toHaveLength(4);
    // Dashed extension: index 3 through 4 (exit) carry a value.
    expect(mustExist(result.extension, "extension segment").filter((p) => "value" in p)).toHaveLength(2);
  });

  it("says the geometry itself is incomplete instead of fabricating it when a required field is absent", () => {
    const times = candleTimes(toCandleSeries(makeCandles()));
    const result = buildUsedLineSegments(times, baseGeometry({ firstIdx: null }), "2026-08-19T23:45:00Z", null);
    expect(result.used).toBeNull();
    expect(result.notes).toContain("geometria da linha incompleta -- linha não desenhada");
  });

  it("says candles do not cover the line's own start when the field is present but out of the fetched range", () => {
    const series = toCandleSeries(makeCandles());
    const times = candleTimes(series);
    // first_idx 3 bars before window start (index -3, well past the tolerance).
    const result = buildUsedLineSegments(times, baseGeometry({ firstIdx: 89 }), "2026-08-19T23:45:00Z", null);
    expect(result.used).toBeNull();
    expect(result.notes).toContain("candles reais não cobrem o início da linha -- trecho sólido não desenhado");
  });

  it("says the operation has no exit yet instead of drawing a fabricated extension", () => {
    const times = candleTimes(toCandleSeries(makeCandles()));
    const result = buildUsedLineSegments(times, baseGeometry(), "2026-08-19T23:45:00Z", null);
    expect(result.used).not.toBeNull();
    expect(result.extension).toBeNull();
    expect(result.notes).toContain("operação sem saída registrada -- extensão pontilhada não desenhada");
  });
});

describe("buildHorizontalSegments: bounded entry/stop/target, never full chart width", () => {
  it("builds one segment per known level, from entry to exit only", () => {
    const times = candleTimes(toCandleSeries(makeCandles()));
    const { segments, notes } = buildHorizontalSegments(times, "2026-08-19T23:45:00Z", "2026-08-20T00:15:00Z", [
      { label: "Entrada", price: "100" },
      { label: "Stop", price: "90" },
      { label: "Alvo", price: null },
    ]);
    expect(notes).toEqual(["sem alvo registrado"]);
    expect(segments).toHaveLength(2);
    const entry = mustExist(segments.find((s) => s.label === "Entrada"), "the Entrada segment");
    expect(entry.points.filter((p) => "value" in p)).toHaveLength(2);
  });

  it("says entry is missing instead of drawing anything when there is no entry timestamp", () => {
    const times = candleTimes(toCandleSeries(makeCandles()));
    const { segments, notes } = buildHorizontalSegments(times, null, "2026-08-20T00:15:00Z", [{ label: "Entrada", price: "100" }]);
    expect(segments).toEqual([]);
    expect(notes).toEqual(["sem entrada registrada -- entrada/stop/alvo não desenhados"]);
  });
});

describe("aggregateTo15m: real 15m OHLCV derived from real 1m candles (T3.49 finding -- no system materializes native 15m)", () => {
  function oneMin(iso: string, o: string, h: string, l: string, c: string, v: string): Candle {
    const t = new Date(iso).getTime();
    return { open_time: iso, close_time: new Date(t + 60_000).toISOString(), open: o, high: h, low: l, close: c, volume: v } as Candle;
  }

  function fullBucket(startIso: string): Candle[] {
    const start = new Date(startIso).getTime();
    return Array.from({ length: 15 }, (_, i) => {
      const iso = new Date(start + i * 60_000).toISOString();
      if (i === 0) return oneMin(iso, "10", "11", "9", "10.5", "1");
      if (i === 1) return oneMin(iso, "10.5", "12", "10", "11", "2");
      if (i === 14) return oneMin(iso, "11", "11.5", "10.8", "11.2", "3");
      return oneMin(iso, "10.9", "11", "10.85", "10.9", "0");
    });
  }

  it("buckets 1m candles into 15m OHLCV: open of the first, high/low extremes, close of the last, volume summed", () => {
    const result = aggregateTo15m(fullBucket("2026-08-19T23:00:00Z"));
    expect(result).toHaveLength(1);
    expect(result[0]).toMatchObject({ open_time: "2026-08-19T23:00:00.000Z", close_time: "2026-08-19T23:15:00.000Z", open: "10", high: "12", low: "9", close: "11.2", volume: "6" });
  });

  it("drops a bucket missing any 1m candle (same `count = 15` rule as the T3.50 export) instead of passing a partial range off as a 15m candle", () => {
    const candles = [
      ...fullBucket("2026-08-19T23:00:00Z"),
      // second bucket, one candle only -- a partial minute range, not a 15m candle.
      oneMin("2026-08-19T23:15:00Z", "11.2", "11.3", "11.1", "11.25", "4"),
    ];
    const result = aggregateTo15m(candles);
    expect(result).toHaveLength(1);
    expect(result[0]?.open_time).toBe("2026-08-19T23:00:00.000Z");
  });

  it("never fabricates a bucket with no 1m candles, and returns [] for an empty page", () => {
    expect(aggregateTo15m([])).toEqual([]);
  });
});

describe("pivotBarIndex / markerIndexNear", () => {
  it("finds the pivot's own bar via the same idx -> time rule as the line", () => {
    const times = candleTimes(toCandleSeries(makeCandles()));
    expect(pivotBarIndex(times, baseGeometry(), "2026-08-19T23:45:00Z")).toBe(1);
  });

  it("finds the exit's own bar by timestamp", () => {
    const times = candleTimes(toCandleSeries(makeCandles()));
    expect(markerIndexNear(times, "2026-08-20T00:15:00Z")).toBe(4);
    expect(markerIndexNear(times, null)).toBeNull();
  });
});
