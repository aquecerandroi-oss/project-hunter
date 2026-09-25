/**
 * Hand-written TypeScript mirror of `hunter_api.schemas.meme_lab` -- same
 * convention as `lib/api/lab-types.ts` (whose own header explains why:
 * `@hunter/shared-types/api` is regenerated from the *whole* OpenAPI surface,
 * so pulling it in for one field would drag in every other schema in flight
 * elsewhere in this shared tree, not just `PullbackOut`). Only the fields the
 * arms board (`components/meme-lab/**`) actually reads are typed; `goal`/
 * `sources`/`real_observed` are real fields of `GET /meme/lab` this module
 * does not need and does not mirror. Every `Decimal` field stays a `string`
 * (CLAUDE.md: money/PnL is never a float).
 */

export interface MemeLabNullableDecimal {
  value: string | null;
  reason: string | null;
}

export interface MemeLabDayScore {
  /** `YYYY-MM-DD`, the Brasília day of entry (`meme_lab_scoreboard_v1`). */
  day: string;
  bets: number;
  closed: number;
  wins: number;
  win_rate: MemeLabNullableDecimal;
  pnl_sol: MemeLabNullableDecimal;
  pnl_usd: MemeLabNullableDecimal;
  unpriced_usd: number;
  r_sum: MemeLabNullableDecimal;
  avg_r: MemeLabNullableDecimal;
  max_drawdown_sol: MemeLabNullableDecimal;
  rugs: number;
  /** T4.16 (`0030`): closes the instrument could not price, already taken out of `wins`/`pnl_sol`/`r_sum`. */
  indeterminate: number;
}

/** T4.91/EXP-M24: the one entry-timing knob a pullback arm turns on -- `null` on a set that still enters at `t0`. */
export interface MemeLabPullback {
  pct: string;
  window_s: number;
}

export interface MemeLabRuleSetCeilings {
  size_sol: string;
  target_x: string;
  trailing_pct: string;
  max_hold_s: number;
  wallet_max_sol: string;
  max_sol_per_bet: string;
  daily_loss_cap_sol: string;
}

export type MemeLabRuleSetKind = "research_only" | "operator";
export const MEME_LAB_RULE_SET_KINDS: readonly MemeLabRuleSetKind[] = ["research_only", "operator"];

export type MemeLabRuleSetStatus = "active" | "retired";
export const MEME_LAB_RULE_SET_STATUSES: readonly MemeLabRuleSetStatus[] = ["active", "retired"];

export interface MemeLabRuleSetBoard {
  id: string;
  name: string;
  version: string;
  kind: MemeLabRuleSetKind;
  exp_ref: string | null;
  status: MemeLabRuleSetStatus;
  code_ref: string;
  ceilings: MemeLabRuleSetCeilings;
  entry_pullback: MemeLabPullback | null;
  today: MemeLabDayScore | null;
  today_reason: string | null;
  /** Newest first, at most `days_limit` (a bounded window, not a paginated list). */
  days: MemeLabDayScore[];
}

export interface MemeLabOut {
  label: string;
  as_of: string;
  day: string;
  days_limit: number;
  rule_sets: MemeLabRuleSetBoard[];
}
