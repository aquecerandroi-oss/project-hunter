import { describe, expect, it } from "vitest";

import {
  durationText,
  EXIT_REASON_LABEL,
  formatDecimalOrReason,
  formatR,
  formatWhenShort,
  reasonLabel,
  signColorClass,
} from "@/components/lab/lab-format";
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

describe("formatWhenShort: one-line 'DD/MM HH:mm', always Brasília (brief T3.17b item 3, timezone updated by brief T3.22)", () => {
  it("renders day/month + hour:minute from a real timestamp, converted to Brasília (-03:00)", () => {
    expect(formatWhenShort("2026-09-08T05:05:05.123456Z")).toBe("08/09 02:05");
  });

  it("pads a single-digit day/month/hour/minute", () => {
    expect(formatWhenShort("2026-01-02T03:04:00Z")).toBe("02/01 00:04");
  });

  it("returns null (never a garbage string) for an invalid timestamp", () => {
    expect(formatWhenShort("not-a-date")).toBeNull();
  });
});

describe("durationText: 'h:mm' only when both timestamps are known (brief T3.17b item 5)", () => {
  it("computes the gap between entry and exit", () => {
    expect(durationText("2026-09-06T00:26:00Z", "2026-09-06T03:41:00Z")).toEqual({ text: "3:15", reason: null });
  });

  it("is '--' with 'sem entrada' when there was no entry at all", () => {
    expect(durationText(null, null)).toEqual({ text: "--", reason: "sem entrada" });
  });

  it("is '--' with 'em aberto' when entry exists but the position never resolved -- never guessed against 'now'", () => {
    expect(durationText("2026-09-06T00:26:00Z", null)).toEqual({ text: "--", reason: "em aberto" });
  });

  it("is '--' with 'intervalo inválido' when the exit somehow precedes the entry", () => {
    expect(durationText("2026-09-06T03:41:00Z", "2026-09-06T00:26:00Z")).toEqual({ text: "--", reason: "intervalo inválido" });
  });
});

describe("EXIT_REASON_LABEL: the 'Saiu' column's own why-it-left vocabulary (brief T3.17b item 5)", () => {
  it("covers every OutcomeResult in lib/api/lab-types.ts", () => {
    expect(EXIT_REASON_LABEL).toEqual({
      target: "alvo",
      stop: "stop",
      expired: "expirou",
      invalidated: "invalidada",
      open: "aberta",
    });
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
