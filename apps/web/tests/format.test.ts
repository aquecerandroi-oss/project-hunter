import { describe, expect, it, vi } from "vitest";

import { compareDecimalStrings, formatBrl, formatBrlSigned, formatCompact, formatMoney, formatPct, formatUtc } from "@/lib/format";

describe("formatMoney", () => {
  it("formats a numeric-string USD amount", () => {
    expect(formatMoney("1234.5")).toBe("$1,234.50");
  });

  it("formats a plain number", () => {
    expect(formatMoney(10)).toBe("$10.00");
  });

  // Production, 12/09/2026 10:3x BRT: the meme desk showed a 0.05 SOL bet as
  // "-18.5 SOL". `roundDecimal` incremented "00184" through BigInt (-> "185"),
  // lost the leading zeros that place the point, and split the wrong digits.
  // Every value below 1 whose kept fraction starts with zeros and rounds up hit it.
  it("keeps the leading zeros of the fraction when rounding up (the -18.5 SOL bug)", () => {
    expect(formatMoney("-0.0184879480", { decimals: 4 })).toBe("-$0.0185");
    expect(formatMoney("-0.0454932120", { decimals: 4 })).toBe("-$0.0455");
    expect(formatMoney("-0.0018775510", { decimals: 4 })).toBe("-$0.0019");
    expect(formatMoney("-0.0375510204", { decimals: 2 })).toBe("-$0.04");
    expect(formatMoney("0.0567", { decimals: 2 })).toBe("$0.06");
    expect(formatMoney("0.00049", { decimals: 4 })).toBe("$0.0005");
  });

  it("still carries across the point when the round-up overflows the kept digits", () => {
    expect(formatMoney("0.99996", { decimals: 4 })).toBe("$1.0000");
    expect(formatMoney("9.999", { decimals: 2 })).toBe("$10.00");
    expect(formatMoney("0.0099996", { decimals: 4 })).toBe("$0.0100");
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

describe("formatBrl: pt-BR grouping (\".\" thousands, \",\" fraction) -- the wallet's first BRL screen (T3.8b polish pass)", () => {
  it("groups thousands with '.' and separates the fraction with ','", () => {
    expect(formatBrl("100725.19")).toBe("R$ 100.725,19");
  });

  it("puts a Unicode minus sign (U+2212) before the 'R$' symbol for a negative amount", () => {
    expect(formatBrl("-1234.5")).toBe("−R$ 1.234,50");
  });

  it("renders an exact zero without any sign", () => {
    expect(formatBrl("0")).toBe("R$ 0,00");
  });

  it("rounds half-up through a carry that propagates across every digit", () => {
    expect(formatBrl("99999.99999999983784")).toBe("R$ 100.000,00");
  });

  it("does not lose precision on a Decimal string above 2^53 (never routes the full value through Number())", () => {
    // 2^53 = 9_007_199_254_740_992; the integer part below is several orders above it.
    expect(formatBrl("12345678901234567.89")).toBe("R$ 12.345.678.901.234.567,89");
  });
});

describe("formatBrlSigned", () => {
  it("adds an explicit '+' for a positive amount", () => {
    expect(formatBrlSigned("725.185185")).toBe("+R$ 725,19");
  });

  it("does not double the sign for a negative amount (formatBrl already carries the '−')", () => {
    expect(formatBrlSigned("-725.185185")).toBe("−R$ 725,19");
  });

  it("does not sign an exact zero", () => {
    expect(formatBrlSigned("0")).toBe("R$ 0,00");
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

describe("formatUtc: the SSR-safe half of a timestamp, independent of the runtime's timezone (H2, T1.5b fix pass) -- now the secondary/tooltip half since brief T3.22 made Brasília the primary text (see tests/time.test.ts)", () => {
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

describe("exponent notation from the API (VPS 2026-09-08: the wallet page crashed on \"0E-20\")", () => {
  it("expands a Python-style zero with scale", () => {
    expect(formatMoney("0E-20")).toBe(formatMoney("0"));
  });
  it("expands positive and negative exponents digit by digit", () => {
    expect(formatMoney("1E+2")).toBe(formatMoney("100"));
    expect(formatMoney("1.5e3")).toBe(formatMoney("1500"));
    expect(formatMoney("-2.5E-1")).toBe(formatMoney("-0.25"));
    expect(formatMoney("123456E-3")).toBe(formatMoney("123.456"));
  });
  it("still refuses garbage", () => {
    expect(() => formatMoney("E5")).toThrow(TypeError);
    expect(() => formatMoney("1E")).toThrow(TypeError);
  });
});

describe("compareDecimalStrings (T3.72b LOW finding #3: exact Decimal-string comparison, never Number())", () => {
  it("orders two plain decimals without ambiguity", () => {
    expect(compareDecimalStrings("60000", "65000")).toBe(-1);
    expect(compareDecimalStrings("65000", "60000")).toBe(1);
    expect(compareDecimalStrings("65000", "65000")).toBe(0);
    expect(compareDecimalStrings("65000", "65000.00")).toBe(0);
  });

  it("stays exact past 2**53, where Number() comparisons can silently flip", () => {
    // Number("90071992547409929") === Number("90071992547409930") once rounded to a double.
    expect(compareDecimalStrings("90071992547409929", "90071992547409930")).toBe(-1);
    expect(Number("90071992547409929") >= Number("90071992547409930")).toBe(true); // the bug this replaces
  });

  it("handles negatives and zero correctly, including a signed zero", () => {
    expect(compareDecimalStrings("-1", "1")).toBe(-1);
    expect(compareDecimalStrings("-0", "0")).toBe(0);
    expect(compareDecimalStrings("-0.5", "-0.25")).toBe(-1);
  });

  it("throws a TypeError on an invalid decimal string, same as parseDecimal's other callers", () => {
    expect(() => compareDecimalStrings("abc", "1")).toThrow(TypeError);
  });
});
