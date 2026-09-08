import { describe, expect, it } from "vitest";

import {
  buildCurveSeries,
  buildScoreboardCardDisplay,
  formatSince,
  maturityBarText,
  maturityRatios,
  noEvaluableReasonText,
  scoreboardStatusLabel,
  sortScoreboardRows,
  verdictBadgeVariant,
  verdictLabel,
  verdictLineColorVar,
  VERDICT_RULE_TEXT,
} from "@/components/lab/lab-scoreboard";
import { buildReferenceRuler, buildWalletRuler } from "@/components/lab/lab-money";
import { exampleCurve, exampleScoreboardRow, makeScoreboardRow } from "@/tests/fixtures/lab";

describe("verdict vocabulary (brief T3.18 item 3: 'inconclusiva muted, validada positive, reprovada negative')", () => {
  it("agrees with 'a versão' in the label (feminine), unlike the API's own masculine field", () => {
    expect(verdictLabel("inconclusivo")).toBe("inconclusiva");
    expect(verdictLabel("validada")).toBe("validada");
    expect(verdictLabel("reprovada")).toBe("reprovada");
  });

  it("maps each verdict to its chip variant", () => {
    expect(verdictBadgeVariant("inconclusivo")).toBe("outline");
    expect(verdictBadgeVariant("validada")).toBe("positive");
    expect(verdictBadgeVariant("reprovada")).toBe("negative");
  });

  it("falls back to the raw code for an unknown verdict, instead of disappearing", () => {
    expect(verdictLabel("desconhecido")).toBe("desconhecido");
    expect(verdictBadgeVariant("desconhecido")).toBe("outline");
    expect(verdictLineColorVar("desconhecido")).toBe("--color-fg-muted");
  });

  it("colours the curve line the same way the card verdict does (brief item 4)", () => {
    expect(verdictLineColorVar("validada")).toBe("--color-green");
    expect(verdictLineColorVar("reprovada")).toBe("--color-red");
    expect(verdictLineColorVar("inconclusivo")).toBe("--color-fg-muted");
  });

  it("always states the rule next to the verdict (brief item 5)", () => {
    expect(VERDICT_RULE_TEXT).toBe("régua: 100 resultados e 30 dias; validada = expectancy > 0 e PF > 1");
  });
});

describe("sortScoreboardRows: active first, then by sum_r descending (brief item 3)", () => {
  it("puts every active version before any non-active one, regardless of sum_r", () => {
    const deprecatedWinner = makeScoreboardRow({ version: { ...exampleScoreboardRow().version, id: "v-dep", status: "deprecated" }, sum_r: { value: "99", reason: null, count: 1, ordered_by: "exit_ts" } });
    const activeLoser = makeScoreboardRow({ version: { ...exampleScoreboardRow().version, id: "v-act", status: "active" }, sum_r: { value: "-5", reason: null, count: 1, ordered_by: "exit_ts" } });

    const sorted = sortScoreboardRows([deprecatedWinner, activeLoser]);
    expect(sorted.map((r) => r.version.id)).toEqual(["v-act", "v-dep"]);
  });

  it("orders two active versions by sum_r descending", () => {
    const better = makeScoreboardRow({ version: { ...exampleScoreboardRow().version, id: "v-better" }, sum_r: { value: "20", reason: null, count: 1, ordered_by: "exit_ts" } });
    const worse = makeScoreboardRow({ version: { ...exampleScoreboardRow().version, id: "v-worse" }, sum_r: { value: "5", reason: null, count: 1, ordered_by: "exit_ts" } });

    expect(sortScoreboardRows([worse, better]).map((r) => r.version.id)).toEqual(["v-better", "v-worse"]);
  });

  it("sorts a version with no sum_r yet last within its own status group, never ahead of a real (even negative) number", () => {
    const withNumber = makeScoreboardRow({ version: { ...exampleScoreboardRow().version, id: "v-number" }, sum_r: { value: "-3", reason: null, count: 1, ordered_by: "exit_ts" } });
    const noSample = makeScoreboardRow({ version: { ...exampleScoreboardRow().version, id: "v-empty" }, sum_r: { value: null, reason: "no_sample", count: 0, ordered_by: "exit_ts" } });

    expect(sortScoreboardRows([noSample, withNumber]).map((r) => r.version.id)).toEqual(["v-number", "v-empty"]);
  });

  it("never mutates the input array", () => {
    const rows = [exampleScoreboardRow()];
    const sorted = sortScoreboardRows(rows);
    expect(sorted).not.toBe(rows);
  });
});

describe("maturityBarText/maturityRatios: '37 de 100 resultados · 2 de 30 dias' (brief item 3, Everton's own example)", () => {
  it("renders the exact Portuguese sentence", () => {
    const maturity = { evaluable: 37, days: 2, threshold: { outcomes: 100, days: 30 }, mature: false };
    expect(maturityBarText(maturity)).toBe("37 de 100 resultados · 2 de 30 dias");
  });

  it("caps both ratios at 100 once a threshold clears", () => {
    const maturity = { evaluable: 150, days: 40, threshold: { outcomes: 100, days: 30 }, mature: true };
    expect(maturityRatios(maturity)).toEqual({ outcomesPct: 100, daysPct: 100 });
  });

  it("computes a partial ratio below the threshold", () => {
    const maturity = { evaluable: 37, days: 2, threshold: { outcomes: 100, days: 30 }, mature: false };
    const { outcomesPct, daysPct } = maturityRatios(maturity);
    expect(outcomesPct).toBeCloseTo(37, 6);
    expect(daysPct).toBeCloseTo(6.6667, 3);
  });
});

describe("formatSince: 'desde DD/MM/AAAA', Brasília (brief T3.22)", () => {
  it("formats a real activation timestamp, converted to Brasília (-03:00) -- 02:08 UTC is still 23:08 the PREVIOUS day in Brasília", () => {
    expect(formatSince("2026-09-06T02:08:13.332014Z")).toBe("desde 05/09/2026");
  });

  it("reads a never-activated version honestly, instead of a blank or a fabricated date", () => {
    expect(formatSince(null)).toBe("ainda não ativada");
  });
});

describe("scoreboardStatusLabel", () => {
  it("translates the known statuses", () => {
    expect(scoreboardStatusLabel("active")).toBe("ativa");
    expect(scoreboardStatusLabel("deprecated")).toBe("descontinuada");
    expect(scoreboardStatusLabel("draft")).toBe("rascunho");
  });
});

describe("noEvaluableReasonText: 'no signals yet / all pending' (brief item 3)", () => {
  it("is null once the version has at least one evaluable outcome", () => {
    expect(noEvaluableReasonText(exampleScoreboardRow({ evaluable: 1 }))).toBeNull();
  });

  it("names pending/no-entry/censored and the unnamed remainder when nothing is evaluable yet", () => {
    const row = exampleScoreboardRow({ emitted: 20, evaluable: 0, pending: 5, no_entry: 3, censored: 2 });
    // remainder = 20 - 0 - 5 - 3 - 2 = 10 (still-open or not-yet-matured outcomes)
    expect(noEvaluableReasonText(row)).toBe(
      "ainda sem resultado avaliável (20 emitidos): 5 pendentes, 10 em acompanhamento ou aguardando maturação, 3 sem entrada, 2 censuradas",
    );
  });

  it("reads a version that only just emitted (everything still open, still tracking) as the unnamed remainder, not a fabricated bucket", () => {
    const row = exampleScoreboardRow({ emitted: 3, evaluable: 0, pending: 0, no_entry: 0, censored: 0 });
    expect(noEvaluableReasonText(row)).toBe("ainda sem resultado avaliável (3 emitidos): 3 em acompanhamento ou aguardando maturação");
  });

  it("falls back to a generic sentence in the (API-impossible) case of zero emitted and zero of every named bucket", () => {
    const row = exampleScoreboardRow({ emitted: 0, evaluable: 0, pending: 0, no_entry: 0, censored: 0 });
    expect(noEvaluableReasonText(row)).toBe("0 sinais emitidos, nenhum ainda avaliável");
  });
});

describe("buildScoreboardCardDisplay: money through the T3.17 ruler + research units", () => {
  const ruler = buildWalletRuler("19333.01", "115998.06");

  it("converts sum_r/expectancy_r into USDT/BRL through the ruler's own risk-per-operation", () => {
    const row = exampleScoreboardRow();
    const display = buildScoreboardCardDisplay(row, ruler);
    expect(display.cumulativeUsdtText).toContain("USDT");
    expect(display.cumulativeUsdtColor).toBe("text-green");
    expect(display.avgUsdtColor).toBe("text-green");
    expect(display.hitRateText).toBe("58.93% (33/56)");
    expect(display.expectancyText).toBe("0.1834R");
    expect(display.pfText).toBe("1.4200");
    expect(display.pfDetail).toBe("+58.4000 / -41.1300 (n=112)");
    expect(display.worstStreakText).toBe("4 perdas seguidas");
    expect(display.maxDrawdownText).toBe("6.1200R");
    expect(display.noEvaluableReason).toBeNull();
  });

  it("shows a negative sum_r/expectancy_r in red, never colored as if positive", () => {
    const row = exampleScoreboardRow({
      sum_r: { value: "-3.9258", reason: null, count: 9, ordered_by: "exit_ts" },
      expectancy_r: { value: "-0.4362", reason: null },
      verdict: "reprovada",
      maturity: { evaluable: 9, days: 1, threshold: { outcomes: 100, days: 30 }, mature: false },
    });
    const display = buildScoreboardCardDisplay(row, ruler);
    expect(display.cumulativeUsdtColor).toBe("text-red");
    expect(display.avgUsdtColor).toBe("text-red");
    expect(display.expectancyColor).toBe("text-red");
  });

  it("shows the reason (never a fabricated 0) when profit_factor is null with no_losses -- a losing side of zero", () => {
    const row = exampleScoreboardRow({ profit_factor: { value: null, reason: "no_losses", sum_positive: "12.0000", sum_negative_abs: "0", sample_size: 9 } });
    const display = buildScoreboardCardDisplay(row, ruler);
    expect(display.pfIsValue).toBe(false);
    expect(display.pfText).toContain("sem perdas");
  });

  it("degrades to buildReferenceRuler's own equity without throwing when there is no wallet", () => {
    const row = exampleScoreboardRow();
    expect(() => buildScoreboardCardDisplay(row, buildReferenceRuler())).not.toThrow();
  });
});

describe("buildCurveSeries: one series per row, coloured by verdict (brief item 4)", () => {
  it("keeps the given (already sorted) row order and attaches each row's own curve", () => {
    const rowA = exampleScoreboardRow({ version: { ...exampleScoreboardRow().version, id: "v-a" }, verdict: "validada" });
    const rowB = exampleScoreboardRow({ version: { ...exampleScoreboardRow().version, id: "v-b" }, verdict: "reprovada" });
    const curvesById = { "v-a": exampleCurve({ strategy_version_id: "v-a" }), "v-b": exampleCurve({ strategy_version_id: "v-b", points: [] }) };

    const series = buildCurveSeries([rowA, rowB], curvesById);
    expect(series.map((s) => s.versionId)).toEqual(["v-a", "v-b"]);
    expect(series[0]?.points.length).toBe(2);
    expect(series[0]?.failed).toBe(false);
    expect(series[1]?.points.length).toBe(0);
    expect(series[1]?.failed).toBe(false);
  });

  it("marks a version's series as failed (never a fabricated flat line) when its own curve fetch returned null", () => {
    const row = exampleScoreboardRow();
    const series = buildCurveSeries([row], { [row.version.id]: null });
    expect(series[0]?.failed).toBe(true);
    expect(series[0]?.points).toEqual([]);
  });

  it("carries the truncated flag through", () => {
    const row = exampleScoreboardRow();
    const series = buildCurveSeries([row], { [row.version.id]: exampleCurve({ truncated: true }) });
    expect(series[0]?.truncated).toBe(true);
  });
});
