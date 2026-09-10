/**
 * `GET /api/v1/orgs/{org_id}/lab/daily-goal` (brief T3.78, frozen schema in
 * `.claude/state/notes-T3.78.md` §1, backed by
 * `apps/api/hunter_api/schemas/lab_daily_goal.py`). Hand-mirrored with `zod`
 * like `manual-orders-types.ts` -- this router has not been through
 * `pnpm gen:types` yet, so there is no generated OpenAPI type to alias. Every
 * money/ratio field is a `DecimalStr` (a plain-notation `Decimal` string,
 * never `0E-20`/`1E+2` -- `lab_common.py::decimal_plain`), kept as `string`
 * here (CLAUDE.md: never `float` for money). Every "no value" is `null` WITH
 * a reason (`fx_reason`, `value_of_1r.reason`, or a `null` progress field
 * whose own docstring in the frozen schema names when it goes `null`) --
 * this file never invents a default for a missing figure, `.parse()` is the
 * boundary that turns a real drift into an honest failure instead of a
 * silently wrong render (same discipline as `manual-orders.ts`).
 */
import { z } from "zod";

// A `Decimal`-backed field the API always sends as a plain-notation string
// (never scientific notation -- `lab_common.py::decimal_plain`). Permissive
// on purpose: this guards against a non-string leaking through, it does not
// re-validate the server's own arithmetic.
const decimalString = z.string().min(1);

/** Same shape as `lib/api/lab-types.ts`'s generated `RateWithCountsOut` (`hunter_api/schemas/lab_scoreboard.py`), reused verbatim by `lab_daily_goal.py`'s `hit_rate` -- hand-mirrored here rather than imported, since this whole file predates `pnpm gen:types` picking up the new router. */
export const dailyGoalRateWithCountsSchema = z.object({
  value: decimalString.nullable(),
  reason: z.string().nullable().optional(),
  numerator: z.number(),
  denominator: z.number(),
});
export type DailyGoalRateWithCounts = z.infer<typeof dailyGoalRateWithCountsSchema>;

export const dailyGoalAxisSchema = z.object({
  used: z.string(),
  pooled_funding_null: z.number(),
  unique_funding_null: z.number(),
});
export type DailyGoalAxis = z.infer<typeof dailyGoalAxisSchema>;

export const dailyGoalPortfolioSchema = z.object({
  equity_usdt: decimalString.nullable(),
  source: z.string(),
});
export type DailyGoalPortfolio = z.infer<typeof dailyGoalPortfolioSchema>;

export const dailyGoalValueOfOneRSchema = z.object({
  label_brl: decimalString,
  real_brl_p10: decimalString.nullable(),
  real_brl_p50: decimalString.nullable(),
  real_brl_p90: decimalString.nullable(),
  sample_size: z.number(),
  reason: z.string().nullable().optional(),
});
export type DailyGoalValueOfOneR = z.infer<typeof dailyGoalValueOfOneRSchema>;

export const dailyGoalProgressSchema = z.object({
  real_brl: decimalString.nullable(),
  label_brl: decimalString,
  distance_to_goal_real_brl: decimalString.nullable(),
  distance_to_goal_label_brl: decimalString,
  required_1r_brl: decimalString.nullable(),
  required_unique_r: decimalString.nullable(),
});
export type DailyGoalProgress = z.infer<typeof dailyGoalProgressSchema>;

export const dailyGoalSeriesPointSchema = z.object({
  day: z.string(),
  unique_r: decimalString,
  pooled_r: decimalString,
});
export type DailyGoalSeriesPoint = z.infer<typeof dailyGoalSeriesPointSchema>;

export const dailyGoalOutSchema = z.object({
  day: z.string(),
  as_of: z.string(),
  axis: dailyGoalAxisSchema,
  dedupe_order: z.string(),
  unique_bets: z.number(),
  pooled_bets: z.number(),
  unique_r: decimalString,
  pooled_r: decimalString,
  hit_rate: dailyGoalRateWithCountsSchema,
  r_per_unique_bet: decimalString.nullable(),
  value_of_1r: dailyGoalValueOfOneRSchema,
  goal_brl: decimalString,
  progress: dailyGoalProgressSchema,
  portfolio: dailyGoalPortfolioSchema,
  fx_reason: z.string().nullable().optional(),
  series_30d: z.array(dailyGoalSeriesPointSchema),
});
export type DailyGoalOut = z.infer<typeof dailyGoalOutSchema>;
