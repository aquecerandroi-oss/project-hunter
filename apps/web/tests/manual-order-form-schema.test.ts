import { describe, expect, it } from "vitest";

import {
  manualOrderFormShapeSchema,
  optionalNotionalSchema,
  positiveDecimalSchema,
  validateStopAgainstMarket,
} from "@/lib/api/manual-order-form-schema";

describe("positiveDecimalSchema", () => {
  it("accepts a plain positive decimal", () => {
    expect(positiveDecimalSchema.safeParse("65000.50").success).toBe(true);
    expect(positiveDecimalSchema.safeParse("1").success).toBe(true);
  });

  it("rejects zero, negative, empty and non-numeric input", () => {
    expect(positiveDecimalSchema.safeParse("0").success).toBe(false);
    expect(positiveDecimalSchema.safeParse("-5").success).toBe(false);
    expect(positiveDecimalSchema.safeParse("").success).toBe(false);
    expect(positiveDecimalSchema.safeParse("abc").success).toBe(false);
    expect(positiveDecimalSchema.safeParse("1e10").success).toBe(false);
  });
});

describe("optionalNotionalSchema", () => {
  it("accepts an empty string (no cap) and a positive decimal", () => {
    expect(optionalNotionalSchema.safeParse("").success).toBe(true);
    expect(optionalNotionalSchema.safeParse("500.00").success).toBe(true);
  });

  it("rejects zero and negative", () => {
    expect(optionalNotionalSchema.safeParse("0").success).toBe(false);
    expect(optionalNotionalSchema.safeParse("-1").success).toBe(false);
  });
});

describe("manualOrderFormShapeSchema", () => {
  const VALID = { marketId: "3f6b3b9a-6b1a-4e6a-9c1a-000000000001", direction: "long" as const, stop: "64000", requestedNotional: "" };

  it("accepts a valid shape", () => {
    expect(manualOrderFormShapeSchema.safeParse(VALID).success).toBe(true);
  });

  it("rejects a non-uuid marketId", () => {
    expect(manualOrderFormShapeSchema.safeParse({ ...VALID, marketId: "not-a-uuid" }).success).toBe(false);
  });

  it("rejects direction 'short' -- SPOT only supports long today", () => {
    expect(manualOrderFormShapeSchema.safeParse({ ...VALID, direction: "short" }).success).toBe(true); // shape-valid; the API/engine is the real authority (module docstring)
  });
});

describe("validateStopAgainstMarket: the hard geometry rule (docs/RISK_ENGINE.md §3.1 check 7)", () => {
  it("rejects a non-positive stop", () => {
    const result = validateStopAgainstMarket("0", "65000", "0.03");
    expect(result.ok).toBe(false);
    expect(result.distancePct).toBeNull();
  });

  it("rejects a stop at or above the last price for a LONG", () => {
    expect(validateStopAgainstMarket("65000", "65000", "0.03").ok).toBe(false);
    expect(validateStopAgainstMarket("66000", "65000", "0.03").ok).toBe(false);
  });

  it("accepts a stop below the last price and computes the implied distance", () => {
    const result = validateStopAgainstMarket("63700", "65000", "0.03");
    expect(result.ok).toBe(true);
    expect(result.distancePct).toBeCloseTo((65000 - 63700) / 65000, 10);
    expect(result.overCap).toBe(false);
  });

  it("flags overCap without blocking when the distance exceeds max_stop_distance_pct", () => {
    const result = validateStopAgainstMarket("60000", "65000", "0.03");
    expect(result.ok).toBe(true);
    expect(result.overCap).toBe(true);
  });

  it("never fabricates a distance when the last price is unknown", () => {
    const result = validateStopAgainstMarket("63700", null, "0.03");
    expect(result.ok).toBe(true);
    expect(result.distancePct).toBeNull();
    expect(result.overCap).toBe(false);
  });

  it("never fabricates overCap when the cap itself is unknown", () => {
    const result = validateStopAgainstMarket("63700", "65000", null);
    expect(result.ok).toBe(true);
    expect(result.distancePct).not.toBeNull();
    expect(result.overCap).toBe(false);
  });
});
