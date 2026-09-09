import { describe, expect, it } from "vitest";

import {
  buildHeadline,
  buildReopenConditions,
  classifyDetector,
  daysBetween,
  disarmReasonLabel,
  formatPctPtBr,
  formatScoreWhole,
  parseBootstrapPointer,
  REOPEN_BASELINE_GATE_TARGET_PCT,
  REOPEN_HISTORY_DAYS_TARGET,
  REOPEN_MARKETS_TARGET,
  WATCHING_THRESHOLD,
} from "@/components/radar/radar-coverage-format";
import { makeRadarCoverage, makeRadarDetector } from "@/tests/fixtures/radar-coverage";

describe("formatScoreWhole", () => {
  it("rounds a Decimal string to a whole pt-BR number", () => {
    expect(formatScoreWhole("38.33")).toBe("38");
  });

  it("stays null for a missing value -- never a fabricated 0", () => {
    expect(formatScoreWhole(null)).toBeNull();
    expect(formatScoreWhole(undefined)).toBeNull();
  });
});

describe("formatPctPtBr", () => {
  it("formats with a comma, one decimal", () => {
    expect(formatPctPtBr("8.08")).toBe("8,1");
  });

  it("stays null for a missing value", () => {
    expect(formatPctPtBr(null)).toBeNull();
  });
});

describe("parseBootstrapPointer", () => {
  it("splits the scanner's raw heartbeat sentence into symbol + progress", () => {
    expect(parseBootstrapPointer("bootstrapping 1000FLOKIUSDT (4/200)")).toEqual({
      symbol: "1000FLOKIUSDT",
      progress: "4/200",
    });
  });

  it("shows an unrecognized shape verbatim rather than dropping it", () => {
    expect(parseBootstrapPointer("something else entirely")).toEqual({
      symbol: "something else entirely",
      progress: "",
    });
  });

  it("is null only when the heartbeat never carried the field", () => {
    expect(parseBootstrapPointer(null)).toBeNull();
    expect(parseBootstrapPointer("")).toBeNull();
  });
});

describe("classifyDetector", () => {
  it("producing wins whenever rows_31d > 0, regardless of a stale disarmed_reason", () => {
    expect(classifyDetector(makeRadarDetector({ rows_31d: 5, disarmed_reason: "funding_unavailable" }))).toBe(
      "producing",
    );
  });

  it("disarmed: zero rows with a declared reason", () => {
    expect(classifyDetector(makeRadarDetector({ rows_31d: 0, disarmed_reason: "funding_unavailable" }))).toBe(
      "disarmed",
    );
  });

  it("silent: zero rows and no declared reason -- the T3.46 defect", () => {
    expect(classifyDetector(makeRadarDetector({ rows_31d: 0, disarmed_reason: null }))).toBe("silent");
  });
});

describe("disarmReasonLabel", () => {
  it("translates a known reason code", () => {
    expect(disarmReasonLabel("funding_unavailable")).toBe("funding indisponível para este mercado");
  });

  it("falls back to a labeled raw code for an unknown reason -- never hidden", () => {
    expect(disarmReasonLabel("something_new")).toBe("motivo técnico: something_new");
  });
});

describe("daysBetween", () => {
  it("computes whole-ish days between two ISO instants", () => {
    expect(daysBetween("2026-09-07T02:24:01Z", "2026-09-08T22:37:00Z")).toBeCloseTo(1.84, 1);
  });

  it("is null when there is no start instant yet (no anomaly ever fired)", () => {
    expect(daysBetween(null, "2026-09-08T22:37:00Z")).toBeNull();
  });
});

describe("buildReopenConditions", () => {
  it("names the exact three T3.46 targets", () => {
    const conditions = buildReopenConditions(makeRadarCoverage());
    expect(conditions.map((c) => c.id)).toEqual(["baselines", "coverage", "history"]);
    expect(conditions[0]?.label).toContain(`${REOPEN_BASELINE_GATE_TARGET_PCT} %`);
    expect(conditions[1]?.label).toContain(`${REOPEN_MARKETS_TARGET}`);
    expect(conditions[2]?.label).toContain(`${REOPEN_HISTORY_DAYS_TARGET}`);
  });

  it("none of the three conditions are met with the real T3.46 numbers", () => {
    const conditions = buildReopenConditions(makeRadarCoverage());
    expect(conditions.every((c) => !c.met)).toBe(true);
  });

  it("baselines condition reads 'sem gate ativo' rather than a fabricated 0% when there is no active weight vector", () => {
    const conditions = buildReopenConditions(makeRadarCoverage({ baseline_gate_v2_pct: null }));
    expect(conditions[0]?.currentText).toBe("sem gate ativo");
    expect(conditions[0]?.pct).toBe(0);
  });

  it("marks a condition met once its real value clears the target", () => {
    const conditions = buildReopenConditions(
      makeRadarCoverage({ markets_with_anomaly: 150 }),
    );
    expect(conditions[1]?.met).toBe(true);
    expect(conditions[1]?.pct).toBe(100);
  });
});

describe("buildHeadline", () => {
  it("includes every real number, in the brief's own clause order", () => {
    const headline = buildHeadline(makeRadarCoverage());
    expect(headline).toContain("cobre 25 de 217 mercados");
    expect(headline).toContain("1000FLOKIUSDT 4/200");
    expect(headline).toContain("baselines prontas");
    expect(headline).toContain(`maior score já visto 38 (primeiro degrau ${WATCHING_THRESHOLD})`);
    expect(headline).toContain("nenhum mercado passou de NORMAL desde");
    expect(headline).toContain("Brasília");
  });

  it("never fabricates a number for a missing field", () => {
    const headline = buildHeadline(
      makeRadarCoverage({ bootstrap_pointer: null, max_score_ever: null, first_anomaly_at: null }),
    );
    expect(headline).toContain("sem heartbeat do scanner no momento");
    expect(headline).toContain("nenhum episódio pontuado ainda");
    expect(headline).toContain("nenhuma anomalia registrada ainda");
  });
});
