import type { UTCTimestamp } from "lightweight-charts";
import { describe, expect, it } from "vitest";

import { alignToUnionTimes, sanitizeCandlePoints, sanitizeLinePoints, sortAndDedupeByTime } from "@/lib/charts/series-data";

const t = (n: number) => n as UTCTimestamp;

describe("sortAndDedupeByTime (T3.31)", () => {
  it("sorts ascending and keeps the last write on a duplicate time", () => {
    const result = sortAndDedupeByTime([
      { time: t(30), tag: "b" },
      { time: t(10), tag: "a" },
      { time: t(10), tag: "a2" },
    ]);
    expect(result.map((p) => p.time)).toEqual([10, 30]);
    expect(result[0]?.tag).toBe("a2");
  });

  it("drops points with a non-finite time", () => {
    const result = sortAndDedupeByTime([{ time: t(NaN) }, { time: t(1) }]);
    expect(result).toEqual([{ time: 1 }]);
  });
});

describe("sanitizeLinePoints (T3.31 -- dev-only lightweight-charts assertions stripped in production)", () => {
  it("drops a non-finite value but keeps a whitespace gap (no `value` key)", () => {
    const result = sanitizeLinePoints([
      { time: t(1), value: NaN },
      { time: t(2), value: 5 },
      { time: t(3) },
    ]);
    expect(result).toEqual([
      { time: 2, value: 5 },
      { time: 3 },
    ]);
  });

  it("sorts and dedupes by time, last write wins", () => {
    const result = sanitizeLinePoints([
      { time: t(2), value: 2 },
      { time: t(1), value: 1 },
      { time: t(1), value: 1.5 },
    ]);
    expect(result).toEqual([
      { time: 1, value: 1.5 },
      { time: 2, value: 2 },
    ]);
  });
});

describe("sanitizeCandlePoints (T3.31)", () => {
  it("drops a candle with any non-finite open/high/low/close", () => {
    const result = sanitizeCandlePoints([
      { time: t(1), open: 1, high: 2, low: 0.5, close: NaN },
      { time: t(2), open: 1, high: 2, low: 0.5, close: 1.5 },
    ]);
    expect(result).toEqual([{ time: 2, open: 1, high: 2, low: 0.5, close: 1.5 }]);
  });
});

describe("alignToUnionTimes (T3.31 root cause: lightweight-charts shares one time scale across every series on a chart)", () => {
  it("backfills every series with a whitespace point at every time only a sibling series has", () => {
    const seriesA = [
      { time: t(1), value: 10 },
      { time: t(2), value: 20 },
    ];
    const seriesB = [
      { time: t(2), value: 200 },
      { time: t(3), value: 300 },
    ];
    const [alignedA, alignedB] = alignToUnionTimes([seriesA, seriesB]);
    expect(alignedA).toEqual([
      { time: 1, value: 10 },
      { time: 2, value: 20 },
      { time: 3 },
    ]);
    expect(alignedB).toEqual([
      { time: 1 },
      { time: 2, value: 200 },
      { time: 3, value: 300 },
    ]);
  });

  it("is a no-op for a single series (the shape every non-Lab chart uses)", () => {
    const only = [
      { time: t(1), value: 1 },
      { time: t(2), value: 2 },
    ];
    const [aligned] = alignToUnionTimes([only]);
    expect(aligned).toEqual(only);
  });
});
