import { describe, expect, it } from "vitest";

import { formatMemePct, formatRatio, formatSol } from "@/components/meme/meme-format";

describe("formatSol", () => {
  it("formats a decimal string with the SOL suffix, never routing through a lossy float for large reserves", () => {
    expect(formatSol("9.713447588")).toBe("9.7134 SOL");
  });

  it("keeps every digit of a value beyond float-safe precision", () => {
    // 2^53 + a fractional remainder that a float would round away.
    expect(formatSol("9007199254740993.123456", 6)).toBe("9,007,199,254,740,993.123456 SOL");
  });
});

describe("formatMemePct", () => {
  it("formats a 0..1 fraction as an unsigned percentage", () => {
    expect(formatMemePct("0.000605")).toBe("0.06%");
  });

  it("formats full coverage as 100%", () => {
    expect(formatMemePct("1", 0)).toBe("100%");
  });
});

describe("formatRatio", () => {
  it("formats a plain ratio to two decimals, no unit", () => {
    expect(formatRatio("1.5")).toBe("1.50");
  });

  it("falls back to the raw string for a non-numeric value rather than throwing", () => {
    expect(formatRatio("not-a-number")).toBe("not-a-number");
  });
});
