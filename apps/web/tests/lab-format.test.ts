import { describe, expect, it } from "vitest";

import { formatDecimalOrReason, formatR, reasonLabel, signColorClass } from "@/components/lab/lab-format";
import { commonAssumedCosts, formatAssumedCosts } from "@/components/lab/lab-costs";
import { makeVersionSummary } from "@/tests/fixtures/lab";

describe("formatDecimalOrReason: null with a reason never renders as a number", () => {
  it("renders the value when present", () => {
    expect(formatDecimalOrReason("0.5000", null)).toEqual({ text: "0.5000", isValue: true });
  });

  it("renders the reason (never '0', never a bare dash) when the value is null", () => {
    const result = formatDecimalOrReason(null, "no_sample");
    expect(result.isValue).toBe(false);
    expect(result.text).not.toBe("0");
    expect(result.text).not.toBe("--");
    expect(result.text).toMatch(/sem amostra/);
  });

  it("still surfaces an unrecognized reason code instead of hiding it", () => {
    const result = formatDecimalOrReason(null, "some_new_reason_code");
    expect(result.isValue).toBe(false);
    expect(result.text).toContain("some_new_reason_code");
  });

  it("falls back to an explicit 'no reason given' rather than an empty string when reason itself is null", () => {
    const result = formatDecimalOrReason(null, null);
    expect(result.isValue).toBe(false);
    expect(result.text.length).toBeGreaterThan(0);
  });
});

describe("formatR", () => {
  it("appends R to a real value, keeping the API's own sign", () => {
    expect(formatR("-1.0421", null)).toEqual({ text: "-1.0421R", isValue: true });
  });

  it("never appends R to a reason string", () => {
    const result = formatR(null, "no_sample");
    expect(result.text.endsWith("R")).toBe(false);
  });
});

describe("reasonLabel", () => {
  it("splits an unlisted prefix:detail reason to keep the known prefix's meaning", () => {
    expect(reasonLabel("gap:failed")).toMatch(/gap:failed/);
  });

  it("labels a fully-known reason", () => {
    expect(reasonLabel("not_applicable")).toBe("não aplicável");
  });
});

describe("signColorClass", () => {
  it("is neutral for an absent value (never green, mirroring MarketRow's rule)", () => {
    expect(signColorClass(null)).toBe("text-fg-muted");
  });

  it("is red for a negative value and green for a non-negative one", () => {
    expect(signColorClass("-1.5")).toBe("text-red");
    expect(signColorClass("1.5")).toBe("text-green");
  });
});

describe("commonAssumedCosts / formatAssumedCosts", () => {
  it("returns the shared costs when every version agrees", () => {
    const versions = [makeVersionSummary(), makeVersionSummary()];
    const common = commonAssumedCosts(versions);
    if (common === null) throw new Error("expected shared assumed costs, got null");
    expect(formatAssumedCosts(common)).toBe("spread 2 bps, slippage 5 bps/lado, taxa 4 bps/lado");
  });

  it("returns null the moment any two versions disagree (Astra's S3b review must-fix)", () => {
    const versions = [
      makeVersionSummary(),
      makeVersionSummary({
        coverage: {
          ...makeVersionSummary().coverage,
          assumed_costs: { assumed_spread_bps: "3", slippage_bps: "5", fee_bps: "4", max_entry_delay_s: 120 },
        },
      }),
    ];
    expect(commonAssumedCosts(versions)).toBeNull();
  });

  it("returns null for an empty version list rather than throwing", () => {
    expect(commonAssumedCosts([])).toBeNull();
  });
});
