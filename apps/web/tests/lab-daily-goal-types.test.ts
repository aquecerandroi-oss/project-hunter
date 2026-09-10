import { describe, expect, it } from "vitest";

import { dailyGoalOutSchema } from "@/lib/api/lab-daily-goal-types";

// The exact "participação morde" example from the frozen contract
// (`.claude/state/notes-T3.78.md` §1) -- parsing the real response the
// backend testcontainer produced, not a guessed shape.
const REAL_EXAMPLE = {
  day: "2026-09-06",
  as_of: "2026-09-10T18:40:00.123456Z",
  axis: { used: "r_net", pooled_funding_null: 0, unique_funding_null: 0 },
  dedupe_order: "activated_at asc, strategy_version_id asc, signal_id asc",
  unique_bets: 1,
  pooled_bets: 1,
  unique_r: "1",
  pooled_r: "1",
  hit_rate: { value: "1", reason: null, numerator: 1, denominator: 1 },
  r_per_unique_bet: "1",
  value_of_1r: {
    label_brl: "250.00",
    real_brl_p10: "140",
    real_brl_p50: "140",
    real_brl_p90: "140",
    sample_size: 1,
    reason: null,
  },
  goal_brl: "9000",
  progress: {
    real_brl: "140",
    label_brl: "250.00",
    distance_to_goal_real_brl: "8860",
    distance_to_goal_label_brl: "8750.00",
    required_1r_brl: "9000",
    required_unique_r: "64.28571428571428571428571429",
  },
  portfolio: { equity_usdt: "20000.0000000000", source: "equity_snapshot" },
  fx_reason: null,
  series_30d: [{ day: "2026-08-08", unique_r: "0", pooled_r: "0" }],
};

describe("dailyGoalOutSchema: parses the frozen contract's real example verbatim", () => {
  it("parses without throwing and keeps every Decimal field a string", () => {
    const parsed = dailyGoalOutSchema.parse(REAL_EXAMPLE);
    expect(typeof parsed.unique_r).toBe("string");
    expect(typeof parsed.goal_brl).toBe("string");
    expect(typeof parsed.value_of_1r.real_brl_p50).toBe("string");
    expect(typeof parsed.progress.required_unique_r).toBe("string");
    expect(parsed.progress.required_unique_r).toBe("64.28571428571428571428571429");
  });

  it("round-trips series_30d as an array of Decimal-string points", () => {
    const parsed = dailyGoalOutSchema.parse(REAL_EXAMPLE);
    expect(parsed.series_30d).toHaveLength(1);
    expect(parsed.series_30d[0]).toEqual({ day: "2026-08-08", unique_r: "0", pooled_r: "0" });
  });
});

describe("dailyGoalOutSchema: null-with-reason branches (FX/sizing absent)", () => {
  it("accepts every real_brl_* null together with a reason, sample_size 0", () => {
    const noFx = {
      ...REAL_EXAMPLE,
      value_of_1r: { label_brl: "250.00", real_brl_p10: null, real_brl_p50: null, real_brl_p90: null, sample_size: 0, reason: "no_fx_observation" },
      progress: {
        ...REAL_EXAMPLE.progress,
        real_brl: null,
        distance_to_goal_real_brl: null,
        required_unique_r: null,
      },
      fx_reason: "no_fx_observation",
    };
    const parsed = dailyGoalOutSchema.parse(noFx);
    expect(parsed.value_of_1r.real_brl_p50).toBeNull();
    expect(parsed.value_of_1r.reason).toBe("no_fx_observation");
    expect(parsed.progress.real_brl).toBeNull();
    expect(parsed.fx_reason).toBe("no_fx_observation");
  });

  it("accepts unique_bets = 0 with r_per_unique_bet null (never a division by zero)", () => {
    const noBets = { ...REAL_EXAMPLE, unique_bets: 0, pooled_bets: 0, r_per_unique_bet: null };
    const parsed = dailyGoalOutSchema.parse(noBets);
    expect(parsed.r_per_unique_bet).toBeNull();
  });

  it("rejects a shape drift (money field sent as a number instead of a Decimal string)", () => {
    const drifted = { ...REAL_EXAMPLE, goal_brl: 9000 };
    expect(() => dailyGoalOutSchema.parse(drifted)).toThrow();
  });
});
