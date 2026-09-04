import { describe, expect, it } from "vitest";

import { formatCompact, formatMoney, formatPct } from "@/lib/format";

describe("formatMoney", () => {
  it("formats a numeric-string USD amount", () => {
    expect(formatMoney("1234.5")).toBe("$1,234.50");
  });

  it("formats a plain number", () => {
    expect(formatMoney(10)).toBe("$10.00");
  });

  it("falls back to zero for a non-numeric string", () => {
    expect(formatMoney("not-a-number")).toBe("$0.00");
  });
});

describe("formatPct", () => {
  it("signs a positive fraction by default", () => {
    expect(formatPct(0.0523)).toBe("+5.23%");
  });

  it("signs a negative fraction", () => {
    expect(formatPct(-0.0523)).toBe("-5.23%");
  });

  it("omits the sign when signed is false", () => {
    expect(formatPct(0.0523, { signed: false })).toBe("5.23%");
  });

  it("respects a custom digit count", () => {
    expect(formatPct(0.05, { digits: 0 })).toBe("+5%");
  });
});

describe("formatCompact", () => {
  it("compacts thousands", () => {
    expect(formatCompact(12500)).toBe("12.5K");
  });

  it("compacts millions", () => {
    expect(formatCompact(2_400_000)).toBe("2.4M");
  });

  it("leaves small numbers unchanged", () => {
    expect(formatCompact(42)).toBe("42");
  });
});
