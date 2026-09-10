import { describe, expect, it } from "vitest";

import {
  axisNoteLine,
  betsCountsLine,
  dailyGoalReasonLabel,
  distanceToGoalLine,
  formatBrlOrReason,
  formatDailyGoalDay,
  goalStatus,
  goalStatusClass,
  hitRateLine,
  requiredLines,
} from "@/components/lab/lab-daily-goal-format";
import type { DailyGoalOut } from "@/lib/api/lab-daily-goal-types";

describe("formatDailyGoalDay: calendar day reshuffle, no timezone math", () => {
  it("reformats YYYY-MM-DD to DD/MM/YYYY", () => {
    expect(formatDailyGoalDay("2026-09-06")).toBe("06/09/2026");
  });

  it("returns '--' for anything that does not match the shape", () => {
    expect(formatDailyGoalDay("not-a-day")).toBe("--");
  });
});

describe("dailyGoalReasonLabel: this endpoint's own reasons, falling back to the shared Lab vocabulary", () => {
  it("labels a reason specific to this endpoint", () => {
    expect(dailyGoalReasonLabel("no_fx_observation")).toMatch(/cotação/);
  });

  it("falls back to the shared lab-format vocabulary for a reason that endpoint already knows", () => {
    expect(dailyGoalReasonLabel("no_completed_operations")).toMatch(/nenhuma operação/);
  });

  it("never hides an unrecognized reason code", () => {
    expect(dailyGoalReasonLabel("brand_new_reason")).toContain("brand_new_reason");
  });
});

describe("formatBrlOrReason: null with a reason, never a fake BRL amount", () => {
  it("formats a real value in BRL", () => {
    const result = formatBrlOrReason("140", null);
    expect(result.isValue).toBe(true);
    expect(result.text).toBe("R$ 140,00");
  });

  it("renders the reason sentence, never '0' or a bare dash, when the value is null", () => {
    const result = formatBrlOrReason(null, "no_fx_observation");
    expect(result.isValue).toBe(false);
    expect(result.text).not.toBe("0");
    expect(result.text).not.toBe("--");
    expect(result.text).toMatch(/cotação/);
  });

  it("falls back to an explicit 'no reason given' when reason itself is null", () => {
    const result = formatBrlOrReason(null, null);
    expect(result.isValue).toBe(false);
    expect(result.text.length).toBeGreaterThan(0);
  });
});

describe("betsCountsLine: unique vs pooled, one-line explanation of the difference", () => {
  it("shows only the two counts when they match (no sibling-version duplicates)", () => {
    expect(betsCountsLine(1, 1)).toBe("1 aposta única · 1 linha somada (pooled)");
  });

  it("names the extra pooled rows explicitly when versions diverge", () => {
    const line = betsCountsLine(1, 3);
    expect(line).toContain("1 aposta única");
    expect(line).toContain("3 linhas somadas (pooled)");
    expect(line).toMatch(/2 linhas extras/);
  });
});

describe("axisNoteLine: names the axis and both exclusion counts without mixing them", () => {
  it("renders the axis name and both funding-null counts", () => {
    const line = axisNoteLine({ used: "r_net", pooled_funding_null: 2, unique_funding_null: 1 });
    expect(line).toContain("r_net");
    expect(line).toContain("2 linhas pooled");
    expect(line).toContain("1 aposta única");
  });
});

describe("hitRateLine: numerator/denominator always shown, null carries a reason", () => {
  it("renders 'n/d (pct%)' when a value is present", () => {
    const result = hitRateLine({ value: "1", reason: null, numerator: 1, denominator: 1 });
    expect(result.isValue).toBe(true);
    expect(result.text).toBe("1/1 (100%)");
  });

  it("renders the reason, never a fabricated 0%, when there is no resolved sample", () => {
    const result = hitRateLine({ value: null, reason: "no_completed_operations", numerator: 0, denominator: 0 });
    expect(result.isValue).toBe(false);
    expect(result.text).not.toContain("0%");
  });
});

function baseProgress(): DailyGoalOut["progress"] {
  return {
    real_brl: "140",
    label_brl: "250.00",
    distance_to_goal_real_brl: "8860",
    distance_to_goal_label_brl: "8750.00",
    required_1r_brl: "9000",
    required_unique_r: "64.28571428571428571428571429",
  };
}

describe("goalStatus / goalStatusClass: green only when a REAL value meets or beats the goal", () => {
  it("is 'unknown' (neutral color) when real_brl is null -- never colored as progress", () => {
    const progress = { ...baseProgress(), real_brl: null };
    expect(goalStatus(progress, "9000")).toBe("unknown");
    expect(goalStatusClass("unknown")).toBe("text-fg-muted");
  });

  it("is 'below' (warning color, never green) when a real value falls short of the goal", () => {
    const status = goalStatus(baseProgress(), "9000");
    expect(status).toBe("below");
    expect(goalStatusClass(status)).toBe("text-warning");
  });

  it("is 'met' (green) only when the real value reaches or beats the goal", () => {
    const progress = { ...baseProgress(), real_brl: "9000" };
    expect(goalStatus(progress, "9000")).toBe("met");
    expect(goalStatusClass("met")).toBe("text-green");
  });
});

describe("distanceToGoalLine: sign-aware wording, never a double negative", () => {
  it("says 'faltam X' below the goal", () => {
    const result = distanceToGoalLine(baseProgress(), "9000", null, null);
    expect(result.isValue).toBe(true);
    expect(result.text).toBe("faltam R$ 8.860,00");
  });

  it("says 'meta batida, sobrou X' (magnitude, not a negative amount) once the real value beats the goal", () => {
    const progress = { ...baseProgress(), real_brl: "9500", distance_to_goal_real_brl: "-500" };
    const result = distanceToGoalLine(progress, "9000", null, null);
    expect(result.isValue).toBe(true);
    expect(result.text).toBe("meta batida, sobrou R$ 500,00");
    expect(result.text).not.toContain("-");
    expect(result.text).not.toContain("−");
  });

  it("renders the reason when distance is null (no real progress known)", () => {
    const progress = { ...baseProgress(), real_brl: null, distance_to_goal_real_brl: null };
    const result = distanceToGoalLine(progress, "9000", "no_fx_observation", null);
    expect(result.isValue).toBe(false);
    expect(result.text).toMatch(/cotação/);
  });
});

describe("requiredLines: 'o que 1 R precisaria valer' / 'quantos R únicos faltariam'", () => {
  it("formats both as real values when the API provides them", () => {
    const { requiredOneR, requiredUniqueR } = requiredLines(baseProgress());
    expect(requiredOneR).toEqual({ text: "R$ 9.000,00", isValue: true });
    expect(requiredUniqueR.isValue).toBe(true);
    expect(requiredUniqueR.text).toBe("64.29 R");
  });

  it("never divides by zero: null unique_r -> a named reason, not a number", () => {
    const progress = { ...baseProgress(), required_1r_brl: null, required_unique_r: null };
    const { requiredOneR, requiredUniqueR } = requiredLines(progress);
    expect(requiredOneR.isValue).toBe(false);
    expect(requiredUniqueR.isValue).toBe(false);
  });
});
