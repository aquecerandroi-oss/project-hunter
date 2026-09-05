import { describe, expect, it } from "vitest";

import { formatSpread } from "@/components/markets/format";

describe("formatSpread", () => {
  it("reads spread_pct as a fraction, not an already-scaled percent (bid 99 / ask 101 -> mid 100 -> 2%)", () => {
    // apps/api's own spread_pct(Decimal("99"), Decimal("101")) == Decimal("0.02"):
    // "bid 99, ask 101 -> mid 100, spread 2 -> 0.02 (2%)". Before the fix,
    // formatSpread just appended "%" to the raw fraction and rendered "0.02%".
    expect(formatSpread("0.02")).toBe("2.000%");
  });

  it("renders a typical perpetual's long-decimal fraction as a short, readable percent", () => {
    expect(formatSpread("0.0001999600079984003199360128")).toBe("0.020%");
  });

  it("never signs a spread (a spread is never negative)", () => {
    expect(formatSpread("0.01")).toBe("1.000%");
  });

  it("shows an honest placeholder for a missing spread", () => {
    expect(formatSpread(null)).toBe("--");
    expect(formatSpread(undefined)).toBe("--");
  });
});
