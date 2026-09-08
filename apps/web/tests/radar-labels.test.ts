import { describe, expect, it } from "vitest";

import { ANOMALY_TYPE_LABEL, anomalyTypeLabel, REGIME_LABEL, STAGE_LABEL, STATUS_LABEL } from "@/components/radar/labels";
import {
  ANOMALY_TYPE_VALUES,
  MARKET_REGIME_VALUES,
  OPPORTUNITY_STAGE_VALUES,
  RADAR_STATUS_VALUES,
} from "@/lib/api/radar-types";

/** No raw enum member (upper-case snake_case) ever reaches the screen -- DESIGN-5 "sem backstage na copy". */
function isCleanLabel(label: string): boolean {
  return !label.includes("_") && label !== label.toUpperCase();
}

describe("STATUS_LABEL: every RADAR_STATUS_VALUES member has a Portuguese label", () => {
  it.each(RADAR_STATUS_VALUES)("%s", (status) => {
    expect(STATUS_LABEL[status]).toBeDefined();
    expect(isCleanLabel(STATUS_LABEL[status])).toBe(true);
  });
});

describe("STAGE_LABEL: every OPPORTUNITY_STAGE_VALUES member has a Portuguese label", () => {
  it.each(OPPORTUNITY_STAGE_VALUES)("%s", (stage) => {
    expect(STAGE_LABEL[stage]).toBeDefined();
    expect(isCleanLabel(STAGE_LABEL[stage])).toBe(true);
  });
});

describe("REGIME_LABEL: every MARKET_REGIME_VALUES member has a Portuguese label", () => {
  it.each(MARKET_REGIME_VALUES)("%s", (regime) => {
    expect(REGIME_LABEL[regime]).toBeDefined();
    expect(isCleanLabel(REGIME_LABEL[regime])).toBe(true);
  });
});

describe("ANOMALY_TYPE_LABEL: every ANOMALY_TYPE_VALUES member has a Portuguese label", () => {
  it.each(ANOMALY_TYPE_VALUES)("%s", (type) => {
    expect(ANOMALY_TYPE_LABEL[type]).toBeDefined();
    expect(isCleanLabel(ANOMALY_TYPE_LABEL[type])).toBe(true);
  });
});

describe("REGIME_LABEL/ANOMALY_TYPE_LABEL: members outside the filter-only lists are still labeled (full schema union, not just the filter subset)", () => {
  it("UNKNOWN regime (MarketRegime's full union has an 11th member the filter list omits)", () => {
    expect(REGIME_LABEL.UNKNOWN).toBe("Sem classificação");
  });

  it("SOCIAL_SPIKE/WHALE_ACTIVITY (Fase 2/3 detectors already in the generated contract)", () => {
    expect(ANOMALY_TYPE_LABEL.SOCIAL_SPIKE).toBeDefined();
    expect(ANOMALY_TYPE_LABEL.WHALE_ACTIVITY).toBeDefined();
  });
});

describe("anomalyTypeLabel: never drops an unrecognized value silently", () => {
  it("labels a known value", () => {
    expect(anomalyTypeLabel("VOLUME_SPIKE")).toBe("Pico de volume");
  });

  it("falls back to the raw value for an unknown one", () => {
    expect(anomalyTypeLabel("SOMETHING_NEW")).toBe("SOMETHING_NEW");
  });
});
