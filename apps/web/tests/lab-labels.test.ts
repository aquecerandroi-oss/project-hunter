import { describe, expect, it } from "vitest";

import {
  evidenceLabel,
  purposeLabel,
  replicationReasonLabel,
  replicationStatusLabel,
  resultLabel,
  statusLabel,
  trackingLabel,
} from "@/components/lab/labels";
import type { OutcomeResult, ShadowTrackingState, StrategyVersionStatus } from "@/lib/api/lab-types";

const STATUSES: StrategyVersionStatus[] = ["draft", "active", "deprecated"];
const PURPOSES = ["research_only", "paper", "live"];
const TRACKING_STATES: ShadowTrackingState[] = ["pending_entry", "active", "terminal", "no_entry", "censored"];
const RESULTS: OutcomeResult[] = ["target", "stop", "expired", "invalidated", "open"];
const REPLICATION_STATUSES = ["promissora", "replicando", "real", "refutada"];

/**
 * Aceite (brief T3.24b): "labels: todo membro de status/purpose/result/
 * tracking tem rótulo em pt sem `_`" -- fails the moment a new enum member
 * ships without a translation here, instead of silently leaking a raw code
 * (docs/DESIGN.md §2, "sem backstage na copy").
 */
describe("components/lab/labels.ts: every domain member has a pt label with no underscore", () => {
  it("status", () => {
    for (const value of STATUSES) {
      const label = statusLabel(value);
      expect(label).not.toBe(value);
      expect(label).not.toMatch(/_/);
    }
  });

  it("purpose", () => {
    for (const value of PURPOSES) {
      const label = purposeLabel(value);
      expect(label).not.toMatch(/_/);
    }
  });

  it("tracking_state", () => {
    for (const value of TRACKING_STATES) {
      const label = trackingLabel(value);
      expect(label).not.toBe(value);
      expect(label).not.toMatch(/_/);
    }
  });

  it("result", () => {
    for (const value of RESULTS) {
      // "stop" is a real word in both languages -- its own label legitimately
      // equals the raw code; every other member must still differ.
      const label = resultLabel(value);
      if (value !== "stop") expect(label).not.toBe(value);
      expect(label).not.toMatch(/_/);
    }
  });

  it("replication status (addendum A2)", () => {
    for (const value of REPLICATION_STATUSES) {
      const label = replicationStatusLabel(value);
      expect(label).not.toMatch(/_/);
    }
  });

  it("evidence (addendum A2)", () => {
    expect(evidenceLabel("prospective")).toBe("prospectivo");
    expect(evidenceLabel("replay")).toBe("replay");
    expect(evidenceLabel("mixed")).toBe("misto");
    expect(evidenceLabel(null)).not.toMatch(/_/);
  });

  it("deprecated renders 'substituída', never the old 'descontinuada'", () => {
    expect(statusLabel("deprecated")).toBe("substituída");
  });

  it("replication reasons split a 'prefix: detail' code and never disappear for an unknown one", () => {
    expect(replicationReasonLabel("sem_irmas")).toBe("sem irmãs ainda");
    expect(replicationReasonLabel("imaturo: 3 de 7 positivas")).toBe("ainda imaturo (3 de 7 positivas)");
    expect(replicationReasonLabel("algo_novo")).toBe("motivo: algo_novo");
  });
});
