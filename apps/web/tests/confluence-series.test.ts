import { describe, expect, it } from "vitest";

import { barIndexContaining } from "@/lib/charts/confluence-series";
import type { UTCTimestamp } from "lightweight-charts";

const TF_15M_S = 15 * 60;

function times(...isos: string[]): UTCTimestamp[] {
  return isos.map((iso) => Math.floor(new Date(iso).getTime() / 1000) as UTCTimestamp);
}

describe("barIndexContaining", () => {
  const series = times("2026-09-23T11:00:00Z", "2026-09-23T11:15:00Z", "2026-09-23T11:30:00Z");

  it("finds the bar that contains an instant inside it", () => {
    expect(barIndexContaining(series, "2026-09-23T11:07:00Z", TF_15M_S)).toBe(0);
    expect(barIndexContaining(series, "2026-09-23T11:22:00Z", TF_15M_S)).toBe(1);
  });

  it("an instant exactly at a bar's open belongs to that bar", () => {
    expect(barIndexContaining(series, "2026-09-23T11:15:00Z", TF_15M_S)).toBe(1);
  });

  it("an instant before the first candle is not covered", () => {
    expect(barIndexContaining(series, "2026-09-23T10:59:00Z", TF_15M_S)).toBeNull();
  });

  it("an instant 20 minutes past the last loaded candle is not covered -- never the last bar", () => {
    // last bar covers [11:30, 11:45); 20 minutes past its open is 11:50, well past its close.
    expect(barIndexContaining(series, "2026-09-23T11:50:00Z", TF_15M_S)).toBeNull();
  });

  it("an instant just inside the last bar's close is still covered", () => {
    expect(barIndexContaining(series, "2026-09-23T11:44:59Z", TF_15M_S)).toBe(2);
  });

  it("an empty series never covers anything", () => {
    expect(barIndexContaining([], "2026-09-23T11:00:00Z", TF_15M_S)).toBeNull();
  });
});
