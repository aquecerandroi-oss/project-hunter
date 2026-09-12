import { describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { dailyGoalOutSchema } from "@/lib/api/lab-daily-goal-types";
import { LabDailyGoalPanel } from "@/components/lab/lab-daily-goal-panel";

vi.mock("@/components/lab/lab-daily-goal-date-picker", () => ({ LabDailyGoalDatePicker: () => null }));
vi.mock("@/components/lab/lab-daily-goal-sparkline", () => ({ LabDailyGoalSparkline: () => null }));

const fixture = {
  day: "2026-09-10", as_of: "2026-09-10T18:00:00Z",
  axis: { used: "r_net", pooled_funding_null: 0, unique_funding_null: 0 },
  dedupe_order: "activated_at asc", unique_bets: 2, pooled_bets: 2,
  unique_r: "1", pooled_r: "1", hit_rate: { value: "0.5", numerator: 1, denominator: 2 },
  r_per_unique_bet: "0.5", goal_brl: "9000",
  value_of_1r: {
    label_brl: "250", real_brl_p10: "50", real_brl_p50: "50", real_brl_p90: "150",
    real_usdt_p10: "10", real_usdt_p50: "10", real_usdt_p90: "30", sample_size: 2,
  },
  progress: {
    real_brl: "50", real_usdt: "10", real_brl_summed: "-50", real_usdt_summed: "-10",
    label_brl: "250", distance_to_goal_real_brl: "8950", distance_to_goal_summed_brl: "9050",
    distance_to_goal_label_brl: "8750", required_1r_brl: "9000", required_unique_r: "180",
  },
  portfolio: { equity_usdt: "20000", source: "equity_snapshot" }, series_30d: [],
};

describe("daily goal without survivor or median-size bias", () => {
  it("keeps the additive sums when parsing", () => {
    const data = dailyGoalOutSchema.parse(fixture);
    expect(data.progress).toMatchObject({ real_brl_summed: "-50", real_usdt_summed: "-10" });
  });

  it("renders the summed loss, summed distance and historical population note", () => {
    const data = dailyGoalOutSchema.parse(fixture);
    const html = renderToStaticMarkup(createElement(LabDailyGoalPanel, { day: data.day, data }));
    expect(html).toContain("-10.00 USDT");
    expect(html).toContain("9.050,00");
    expect(html).toContain("versões ativas em cada dia");
    expect(html).toContain("p50");
    expect(html).not.toContain("nenhuma ordem foi");
  });

  it("accepts an old API without pretending the estimate is a sum", () => {
    const oldProgress = { ...fixture.progress, real_brl_summed: undefined, real_usdt_summed: undefined };
    const data = dailyGoalOutSchema.parse({ ...fixture, progress: oldProgress });
    const html = renderToStaticMarkup(createElement(LabDailyGoalPanel, { day: data.day, data }));
    expect(html).toContain("soma por aposta indisponível");
  });
});
