import { describe, expect, it, vi } from "vitest";

import { formatCompact, formatLocalOffset, formatMoney, formatPct, formatUtc, formatUtcWithOffset } from "@/lib/format";

describe("formatMoney", () => {
  it("formats a numeric-string USD amount", () => {
    expect(formatMoney("1234.5")).toBe("$1,234.50");
  });

  it("formats a plain number", () => {
    expect(formatMoney(10)).toBe("$10.00");
  });

  it("does not lose precision on a 28-digit Decimal string (never routes the full value through Number())", () => {
    expect(formatMoney("123456789012345678.1234567890")).toBe("$123,456,789,012,345,678.12");
  });

  it("formats an exact sub-cent amount when more decimals are requested", () => {
    expect(formatMoney("0.0000000001", { decimals: 10 })).toBe("$0.0000000001");
  });

  it("formats negative values with the sign outside the currency symbol", () => {
    expect(formatMoney("-1234.5")).toBe("-$1,234.50");
  });

  it("rounds half-up at the requested decimal count", () => {
    expect(formatMoney("1.005", { decimals: 2 })).toBe("$1.01");
  });

  it("throws a TypeError instead of producing NaN output for an invalid string", () => {
    expect(() => formatMoney("not-a-number")).toThrow(TypeError);
  });

  it("throws a TypeError for a non-finite number", () => {
    expect(() => formatMoney(Number.NaN)).toThrow(TypeError);
    expect(() => formatMoney(Number.POSITIVE_INFINITY)).toThrow(TypeError);
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

describe("formatUtcWithOffset: time is always UTC, with the local offset visible (no hover required)", () => {
  it("shows the UTC clock matching the ISO timestamp's own UTC components", () => {
    const iso = "2026-09-05T14:32:10.000Z";
    const result = formatUtcWithOffset(iso);
    expect(result).toContain("14:32:10 UTC");
  });

  it("always includes a visible, signed local offset in parentheses -- never only in a title attribute", () => {
    const result = formatUtcWithOffset("2026-09-05T14:32:10.000Z");
    expect(result).toMatch(/\(\d{2}:\d{2}:\d{2} [+-]\d{2}:\d{2}\)$/);
  });

  it("returns an honest placeholder for an invalid timestamp instead of 'Invalid Date'", () => {
    expect(formatUtcWithOffset("not-a-timestamp")).toBe("--");
  });
});

describe("formatUtc: the SSR-safe half of a timestamp, independent of the runtime's timezone (H2, T1.5b fix pass)", () => {
  it("never calls Date#getTimezoneOffset -- only reads the UTC components of the ISO string", () => {
    // A regression here is exactly what caused the hydration mismatch: any
    // reliance on the runtime's own zone makes the output depend on WHERE
    // this function runs (server container vs. browser), not just WHAT
    // timestamp it was given -- unlike `formatLocalOffset`, `formatUtc` must
    // produce the identical string no matter which environment calls it.
    const spy = vi.spyOn(Date.prototype, "getTimezoneOffset");
    const result = formatUtc("2026-09-05T14:32:10.000Z");
    expect(result).toBe("14:32:10 UTC");
    expect(spy).not.toHaveBeenCalled();
    spy.mockRestore();
  });

  it("returns an honest placeholder for an invalid timestamp", () => {
    expect(formatUtc("not-a-timestamp")).toBe("--");
  });
});

describe("formatLocalOffset: the client-only enhancement half, never rendered during SSR", () => {
  it("returns a signed local time distinct from the UTC clock", () => {
    const result = formatLocalOffset("2026-09-05T14:32:10.000Z");
    expect(result).toMatch(/^\d{2}:\d{2}:\d{2} [+-]\d{2}:\d{2}$/);
  });

  it("returns null (not '--') for an invalid timestamp, so a caller can safely fall back to formatUtc alone", () => {
    expect(formatLocalOffset("not-a-timestamp")).toBeNull();
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

  it("falls back to decimal-safe (non-compact) grouped output above 2^53", () => {
    // 2^53 = 9_007_199_254_740_992; one order of magnitude above is unsafe for Number.
    expect(formatCompact("123456789012345678.99")).toBe("123,456,789,012,345,678.99");
  });
});
