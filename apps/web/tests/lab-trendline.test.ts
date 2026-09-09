import { describe, expect, it } from "vitest";

import {
  asOfFromPatternBars,
  computeCandleWindow,
  eventKindLabel,
  extractTrendlineGeometry,
  lineKindLabel,
  linePriceAtIdx,
  linePriceAtTimeMs,
  lineTimeMsForIdx,
  parseFeatureMap,
  type TrendlineGeometry,
} from "@/lib/lab-trendline";
import { exampleTrendlineSupportingFeatures } from "@/tests/fixtures/lab-trendline";

// Narrow instead of `!` (no-non-null-assertion): fail with a clear message
// rather than assert past a genuinely absent geometry.
function mustGeometry(geometry: TrendlineGeometry | null): TrendlineGeometry {
  if (!geometry) throw new Error("expected extractTrendlineGeometry to return a geometry");
  return geometry;
}

describe("parseFeatureMap / extractTrendlineGeometry: the real trendline_breakout v1 envelope (VPS, T3.34c q05)", () => {
  it("parses every persisted geometry field from the real envelope shape, values only", () => {
    const result = extractTrendlineGeometry(exampleTrendlineSupportingFeatures());
    expect(result.present).toBe(true);
    expect(result.missing).toEqual([]);
    const g = mustGeometry(result.geometry);
    expect(g.lineKind).toBe("support");
    expect(g.lineId).toBe("03422055d14efe64");
    expect(g.slopePerBar).toBeCloseTo(0.0001217142857142857, 15);
    expect(g.touches).toBe(3);
    expect(g.violations).toBe(0);
    expect(g.firstIdx).toBe(57);
    expect(g.lastIdx).toBe(92);
    expect(g.validFromIdx).toBe(95);
    expect(g.priceAtDecision).toBeCloseTo(0.07470514285714286, 12);
    expect(g.eventKind).toBe("bounce");
    expect(g.eventDistanceAtr).toBeCloseTo(0.7295685515803986, 12);
    expect(g.pivotLowPrice).toBeCloseTo(0.07434, 10);
    expect(g.pivotLowIdx).toBe(92);
    expect(g.patternBars).toBe(96);
    expect(g.patternPivots).toBe(13);
    expect(g.patternLines).toBe(2);
    expect(g.patternRetiredLines).toBe(0);
    // `channel_width_atr` is a legitimate `null` here (no channel found) -- not a missing field.
    expect(g.channelAvailable).toBe(false);
    expect(g.channelWidthAtr).toBeNull();
    expect(g.patternParams).toEqual({
      angle_bucket_atr: "0.1",
      atr_period: "14",
      bounce_atr: "0.5",
      bounce_bars: "3",
      break_atr: "0.5",
      level_bucket_atr: "0.5",
      max_anchors: "20",
      max_channels: "3",
      max_lines: "6",
      min_swing_atr: "1",
      min_touches: "3",
      parallel_tol: "0.05",
      pivot_k: "3",
      retest_bars: "10",
      retire_after_break: true,
      rvol_min: null,
      tolerance_atr: "0.25",
    });
  });

  it("returns present:false (never an error) for a strategy that carries no line at all", () => {
    const result = extractTrendlineGeometry({ features: [{ name: "rsi_14", value: "62.3" }] });
    expect(result).toEqual({ present: false, geometry: null, missing: [] });
  });

  it("returns present:false for null/malformed envelopes without throwing", () => {
    expect(extractTrendlineGeometry(null)).toEqual({ present: false, geometry: null, missing: [] });
    expect(extractTrendlineGeometry({})).toEqual({ present: false, geometry: null, missing: [] });
    expect(parseFeatureMap(null)).toBeNull();
    expect(parseFeatureMap({ features: "not-an-array" })).toBeNull();
  });

  it("lists the Portuguese label of any field that fails to parse, without dropping the fields that did (never fabricated, never hidden)", () => {
    const broken = exampleTrendlineSupportingFeatures();
    const features = (broken.features as { name: string; value: unknown }[]).map((f) => (f.name === "line_touches" ? { ...f, value: "not-a-number" } : f));
    const result = extractTrendlineGeometry({ ...broken, features });
    expect(result.present).toBe(true);
    expect(result.missing).toContain("toques");
    const g = mustGeometry(result.geometry);
    expect(g.touches).toBeNull();
    expect(g.lineId).toBe("03422055d14efe64");
  });
});

describe("lineKindLabel / eventKindLabel: pt-BR, total function", () => {
  it("translates the two known line kinds and event kinds", () => {
    expect(lineKindLabel("support")).toBe("suporte");
    expect(lineKindLabel("resistance")).toBe("resistência");
    expect(eventKindLabel("bounce")).toBe("repique");
    expect(eventKindLabel("breakout")).toBe("rompimento");
  });

  it("still renders (never disappears) for an unrecognized code", () => {
    expect(lineKindLabel("weird")).toBe("weird");
    expect(lineKindLabel(null)).toBe("desconhecido");
  });
});

describe("asOfFromPatternBars / lineTimeMsForIdx / linePriceAtIdx / linePriceAtTimeMs: T3.34c's own formulas", () => {
  it("as_of = pattern_bars - 1", () => {
    expect(asOfFromPatternBars(96)).toBe(95);
  });

  it("idx -> bar time: decision_bar_close - (as_of - idx) * 15min", () => {
    const decisionBarClose = "2026-08-19T23:45:00Z";
    const asOf = 95;
    expect(lineTimeMsForIdx(decisionBarClose, asOf, 95)).toBe(new Date(decisionBarClose).getTime());
    expect(lineTimeMsForIdx(decisionBarClose, asOf, 57)).toBe(new Date("2026-08-19T14:15:00Z").getTime());
    expect(lineTimeMsForIdx(decisionBarClose, asOf, 92)).toBe(new Date("2026-08-19T23:00:00Z").getTime());
  });

  it("price(i) = price_at_decision + slope_per_bar * (i - as_of)", () => {
    expect(linePriceAtIdx(100, 2, 95, 95)).toBe(100);
    expect(linePriceAtIdx(100, 2, 90, 95)).toBe(90);
    expect(linePriceAtIdx(100, 2, 100, 95)).toBe(110);
  });

  it("linePriceAtTimeMs matches linePriceAtIdx at exact bar boundaries, and extrapolates linearly between them", () => {
    const decisionBarClose = "2026-08-19T23:45:00Z";
    const decisionMs = new Date(decisionBarClose).getTime();
    const line = { priceAtDecision: 100, slopePerBar: 2 };
    expect(linePriceAtTimeMs(line, decisionBarClose, decisionMs)).toBe(100);
    expect(linePriceAtTimeMs(line, decisionBarClose, decisionMs + 15 * 60_000)).toBe(102);
    expect(linePriceAtTimeMs(line, decisionBarClose, decisionMs + 30 * 60_000)).toBe(104);
  });
});

describe("computeCandleWindow: a real historical window, never 'now'", () => {
  it("covers the whole pattern through the exit, with a small forward margin", () => {
    const window = computeCandleWindow("2026-08-19T23:45:00Z", 96, "2026-08-20T04:30:00Z");
    // exit is 4h45m (19 bars) after the decision bar; +4 bars margin +1 bar for `before`'s strict '<'.
    expect(new Date(window.beforeIso).toISOString()).toBe("2026-08-20T05:45:00.000Z");
    expect(window.limit).toBe(96 + 19 + 4 + 2);
  });

  it("extends a fixed, small amount past the decision bar (never 'now') when there is no exit yet", () => {
    const window = computeCandleWindow("2026-08-19T23:45:00Z", 96, null);
    expect(new Date(window.beforeIso).toISOString()).toBe("2026-08-20T02:00:00.000Z");
    expect(window.limit).toBe(96 + 0 + 8 + 2);
  });

  it("never exceeds the API's own MAX_CANDLES_LIMIT (apps/api/hunter_api/routers/markets.py)", () => {
    const window = computeCandleWindow("2026-08-19T23:45:00Z", 96, "2027-01-01T00:00:00Z");
    expect(window.limit).toBe(1500);
  });
});
