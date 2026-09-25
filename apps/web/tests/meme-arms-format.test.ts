import { describe, expect, it } from "vitest";

import { avgR, evaluableClosed, sortRuleSets, sumDecimalStrings, sumWindow } from "@/components/meme-lab/meme-arms-format";
import type { MemeLabDayScore, MemeLabRuleSetBoard } from "@/lib/api/meme-lab-types";

function day(overrides: Partial<MemeLabDayScore> = {}): MemeLabDayScore {
  return {
    day: "2026-09-24",
    bets: 1,
    closed: 1,
    wins: 1,
    win_rate: { value: "1", reason: null },
    pnl_sol: { value: "0.01", reason: null },
    pnl_usd: { value: "1", reason: null },
    unpriced_usd: 0,
    r_sum: { value: "1", reason: null },
    avg_r: { value: "1", reason: null },
    max_drawdown_sol: { value: "0", reason: null },
    rugs: 0,
    indeterminate: 0,
    ...overrides,
  };
}

function ruleSet(overrides: Partial<MemeLabRuleSetBoard> = {}): MemeLabRuleSetBoard {
  return {
    id: "01994d00-6c1a-7000-8000-000000000001",
    name: "meme_paper_v0",
    version: "1",
    kind: "research_only",
    exp_ref: null,
    status: "active",
    code_ref: "hunter_indicators.meme.rules:evaluate_entry+evaluate_exit",
    ceilings: {
      size_sol: "0.05",
      target_x: "2",
      trailing_pct: "30",
      max_hold_s: 900,
      wallet_max_sol: "2",
      max_sol_per_bet: "0.05",
      daily_loss_cap_sol: "0.2",
    },
    entry_pullback: null,
    today: null,
    today_reason: "no_bets_today",
    days: [],
    ...overrides,
  };
}

describe("sumDecimalStrings", () => {
  it("sums exact decimals of different scales without float drift", () => {
    expect(sumDecimalStrings(["0.1", "0.02", "1"])).toBe("1.12");
  });

  it("keeps the sign of a net loss", () => {
    expect(sumDecimalStrings(["0.05", "-0.20", "0.02"])).toBe("-0.13");
  });

  it("is 0 for an empty window (never a crash)", () => {
    expect(sumDecimalStrings([])).toBe("0");
  });
});

describe("sumWindow", () => {
  it("adds entries/closed/wins/indeterminate and the measured pnl_sol/r_sum across days", () => {
    const days = [
      day({ bets: 3, closed: 2, wins: 1, pnl_sol: { value: "0.10", reason: null }, r_sum: { value: "1.5", reason: null }, indeterminate: 1 }),
      day({ bets: 1, closed: 1, wins: 1, pnl_sol: { value: "0.02", reason: null }, r_sum: { value: "0.5", reason: null } }),
    ];
    const totals = sumWindow(days);
    expect(totals).toEqual({ entries: 4, closed: 3, wins: 2, indeterminate: 1, netSol: "0.12", rSum: "2.0" });
  });

  it("skips a day whose pnl_sol/r_sum has no value (no closed bets that day) instead of treating it as 0 silently breaking the sum", () => {
    const days = [day({ pnl_sol: { value: null, reason: "no_closed_bets" }, r_sum: { value: null, reason: "no_closed_bets" }, closed: 0, wins: 0 })];
    expect(sumWindow(days).netSol).toBe("0");
    expect(sumWindow(days).rSum).toBe("0");
  });

  it("is all-zero for a rule set with no days on record yet", () => {
    expect(sumWindow([])).toEqual({ entries: 0, closed: 0, wins: 0, indeterminate: 0, netSol: "0", rSum: "0" });
  });
});

describe("evaluableClosed", () => {
  it("subtracts indeterminate from closed -- `closed` alone counts bets pnl_sol/r_sum already exclude", () => {
    expect(evaluableClosed({ closed: 3, indeterminate: 1 })).toBe(2);
  });

  it("is 0, never negative, when every close was indeterminate", () => {
    expect(evaluableClosed({ closed: 1, indeterminate: 1 })).toBe(0);
  });
});

describe("avgR", () => {
  it("is the average R-multiple over the evaluable bets -- holds across differently-sized legs, unlike a fixed-stake percentage", () => {
    expect(avgR("1.5", 2)).toBeCloseTo(0.75, 10);
  });

  it("is negative for a net losing window", () => {
    expect(avgR("-0.8", 2)).toBeCloseTo(-0.4, 10);
  });

  it("is null without an evaluable bet -- never a division by zero", () => {
    expect(avgR("0", 0)).toBeNull();
    expect(avgR("0", -1)).toBeNull();
  });
});

describe("sortRuleSets", () => {
  it("puts active rule sets before retired ones, then orders by name/version", () => {
    const b = ruleSet({ id: "b", name: "recuo_v1", version: "1" });
    const a = ruleSet({ id: "a", name: "operator", version: "5" });
    const retired = ruleSet({ id: "r", name: "old", version: "1", status: "retired" });
    expect(sortRuleSets([retired, b, a]).map((r) => r.id)).toEqual(["a", "b", "r"]);
  });
});
