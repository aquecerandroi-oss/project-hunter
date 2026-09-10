import { describe, expect, it } from "vitest";

import {
  formatLatencySeconds,
  LATENCY_HOP_VALUES,
  latencyHopLabel,
  latencyStatusBadgeVariant,
  latencyStatusLabel,
  latencyUnknownReason,
} from "@/components/system/latency-labels";
import { LATENCY_SLO_STATUS_VALUES } from "@/lib/api/latency-types";

function isCleanLabel(label: string): boolean {
  return !label.includes("_") && label !== label.toUpperCase();
}

describe("latencyHopLabel: every LATENCY_HOP_VALUES member has a clean Portuguese label", () => {
  it.each(LATENCY_HOP_VALUES)("%s", (hop) => {
    expect(isCleanLabel(latencyHopLabel(hop))).toBe(true);
  });

  it("never drops an unrecognized hop silently", () => {
    expect(latencyHopLabel("some_new_hop")).toBe("some_new_hop");
  });
});

describe("latencyUnknownReason: every LATENCY_HOP_VALUES member has a reason, never blank", () => {
  it.each(LATENCY_HOP_VALUES)("%s", (hop) => {
    expect(latencyUnknownReason(hop).length).toBeGreaterThan(0);
  });

  it("falls back to a generic honest reason for an unrecognized hop", () => {
    expect(latencyUnknownReason("some_new_hop")).toBe("sem leitura ainda");
  });
});

describe("latencyStatusLabel/latencyStatusBadgeVariant: every LatencySloStatus is mapped, critical is always the negative (red) variant", () => {
  it.each(LATENCY_SLO_STATUS_VALUES)("%s", (status) => {
    expect(latencyStatusLabel(status).length).toBeGreaterThan(0);
  });

  it("maps ok/warn/critical/unknown to positive/warning/negative/default", () => {
    expect(latencyStatusBadgeVariant("ok")).toBe("positive");
    expect(latencyStatusBadgeVariant("warn")).toBe("warning");
    expect(latencyStatusBadgeVariant("critical")).toBe("negative");
    expect(latencyStatusBadgeVariant("unknown")).toBe("default");
  });
});

describe("formatLatencySeconds", () => {
  it("always shows two decimals with a trailing 's', tabular-nums friendly", () => {
    expect(formatLatencySeconds(0.09)).toBe("0.09s");
    expect(formatLatencySeconds(180)).toBe("180.00s");
    expect(formatLatencySeconds(3.9)).toBe("3.90s");
  });
});
