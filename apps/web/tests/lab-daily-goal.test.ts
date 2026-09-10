import { beforeEach, describe, expect, it, vi } from "vitest";

// `server-only` throws when imported outside Next's real "react-server"
// build condition, which Vitest never sets (see tests/invitations-actions.test.ts / tests/lab.test.ts).
vi.mock("server-only", () => ({}));

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }));
vi.mock("@/lib/server/api", () => ({ apiFetch: apiFetchMock }));

import { getLabDailyGoal } from "@/lib/api/lab-daily-goal";

const MINIMAL_VALID_RESPONSE = {
  day: "2026-09-10",
  as_of: "2026-09-10T18:40:00Z",
  axis: { used: "r_net", pooled_funding_null: 0, unique_funding_null: 0 },
  dedupe_order: "activated_at asc, strategy_version_id asc, signal_id asc",
  unique_bets: 0,
  pooled_bets: 0,
  unique_r: "0",
  pooled_r: "0",
  hit_rate: { value: null, reason: "no_completed_operations", numerator: 0, denominator: 0 },
  r_per_unique_bet: null,
  value_of_1r: { label_brl: "250.00", real_brl_p10: null, real_brl_p50: null, real_brl_p90: null, sample_size: 0, reason: "no_bets" },
  goal_brl: "9000",
  progress: {
    real_brl: null,
    label_brl: "0",
    distance_to_goal_real_brl: null,
    distance_to_goal_label_brl: "9000",
    required_1r_brl: null,
    required_unique_r: null,
  },
  portfolio: { equity_usdt: null, source: "no_portfolio" },
  fx_reason: null,
  series_30d: [],
};

beforeEach(() => {
  apiFetchMock.mockReset().mockResolvedValue(MINIMAL_VALID_RESPONSE);
});

describe("getLabDailyGoal: path and query building", () => {
  it("calls the org-scoped daily-goal endpoint with no query string when `day` is omitted", async () => {
    await getLabDailyGoal("org-1");
    expect(apiFetchMock).toHaveBeenCalledWith("/api/v1/orgs/org-1/lab/daily-goal");
  });

  it("serializes `day` when given", async () => {
    await getLabDailyGoal("org-1", { day: "2026-09-06" });
    expect(apiFetchMock).toHaveBeenCalledWith("/api/v1/orgs/org-1/lab/daily-goal?day=2026-09-06");
  });
});

describe("getLabDailyGoal: response validation", () => {
  it("returns the parsed response on a valid shape", async () => {
    const result = await getLabDailyGoal("org-1");
    expect(result.goal_brl).toBe("9000");
    expect(result.value_of_1r.reason).toBe("no_bets");
  });

  it("throws instead of silently returning a malformed response", async () => {
    apiFetchMock.mockResolvedValue({ ...MINIMAL_VALID_RESPONSE, goal_brl: 9000 });
    await expect(getLabDailyGoal("org-1")).rejects.toThrow();
  });
});
