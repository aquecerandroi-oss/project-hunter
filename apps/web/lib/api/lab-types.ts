/**
 * TypeScript mirror of the Shadow Lab API schemas (S3a, already implemented
 * and tested against real data -- `apps/api/hunter_api/schemas/lab_*.py`).
 * `packages/shared-types/src/generated/api.d.ts` does not have a `lab`
 * namespace yet (types have not been regenerated since S3a landed), so
 * these are hand-written against the actual Pydantic models, not guessed
 * from the contract doc alone. Every Decimal field is a `string` (never
 * `number` -- CLAUDE.md: money/PnL/R is never `float`).
 */

export type StrategyVersionStatus = "draft" | "active" | "deprecated";
export type OutcomeResult = "target" | "stop" | "expired" | "invalidated" | "open";
export type ShadowTrackingState = "pending_entry" | "active" | "terminal" | "no_entry" | "censored";

/** A rate/expectancy that is `null` with a reason instead of a silent zero. */
export interface NullableMetric {
  value: string | null;
  reason: string | null;
}

/** PF always carries its denominator, even when `value` is null (Astra must-fix 3). */
export interface ProfitFactorOut {
  value: string | null;
  reason: string | null;
  sum_positive: string;
  sum_negative_abs: string;
  sample_size: number;
}

export interface SumOfROut {
  value: string | null;
  reason: string | null;
  count: number;
  ordered_by: string;
}

export interface NoEntryCounts {
  total: number;
  by_reason: Record<string, number>;
}

export interface TerminalCounts {
  total: number;
  by_result: Record<string, number>;
}

export interface CensoredCounts {
  total: number;
  by_reason: Record<string, number>;
}

export interface VersionCounts {
  decisions: null;
  decisions_reason: string;
  signals_emitted: number;
  pending_entry: number;
  entered: number;
  no_entry: NoEntryCounts;
  active: number;
  terminal: TerminalCounts;
  censored: CensoredCounts;
  funding_not_settleable: number;
}

export interface RExFundingCoverage {
  evaluable_outcomes: number;
  r_net_evaluable_outcomes: number;
}

export interface VersionMetrics {
  target_rate_among_resolved_touches: NullableMetric;
  net_profit_rate: NullableMetric;
  hypothetical_net_expectancy_r: NullableMetric;
  profit_factor: ProfitFactorOut;
  sum_of_hypothetical_r: SumOfROut;
}

export interface RExFundingBlock {
  net_profit_rate: NullableMetric;
  hypothetical_net_expectancy_r: NullableMetric;
  profit_factor: ProfitFactorOut;
  sum_of_hypothetical_r: SumOfROut;
  coverage: RExFundingCoverage;
}

export interface MaturityOut {
  evaluable_outcomes: number;
  distinct_days: number;
  inconclusive: boolean;
}

export interface AssumedCostsOut {
  assumed_spread_bps: string | null;
  slippage_bps: string | null;
  fee_bps: string | null;
  max_entry_delay_s: number | null;
}

export interface CoverageOut {
  markets_with_signals: number;
  distinct_days: number;
  note: string;
  assumed_costs: AssumedCostsOut;
}

export interface VersionSummaryOut {
  strategy_version_id: string;
  strategy_key: string;
  version: string;
  code_ref: string | null;
  status: StrategyVersionStatus;
  activated_at: string | null;
  deprecated_at: string | null;
  counts: VersionCounts;
  metrics: VersionMetrics;
  r_ex_funding: RExFundingBlock;
  portfolio_pnl: null;
  portfolio_pnl_reason: string;
  portfolio_max_drawdown: null;
  portfolio_max_drawdown_reason: string;
  maturity: MaturityOut;
  coverage: CoverageOut;
}

export interface LabSummaryOut {
  as_of: string;
  window: string;
  cohort: string;
  label: string;
  versions: VersionSummaryOut[];
}

export interface VersionOut {
  strategy_version_id: string;
  strategy_key: string;
  version: string;
  status: StrategyVersionStatus;
  code_ref: string | null;
  activated_at: string | null;
  deprecated_at: string | null;
  /** Best-effort, regex-reconstructed from `changelog` -- never an identity (contract-S3-lab.md). */
  superseded_by: string | null;
  params_hash: string;
  default_parameters: Record<string, unknown>;
}

export interface LabVersionsOut {
  items: VersionOut[];
}

export interface SignalListItemOut {
  signal_id: string;
  strategy_version_id: string;
  market: string;
  cohort: string;
  decision_at: string;
  source_bar_close: string;
  reference_price: string | null;
  stop: string | null;
  target1: string | null;
  entry_plan: Record<string, unknown>;
  virtual_entry: string | null;
  entry_ts: string | null;
  exit_price: string | null;
  exit_ts: string | null;
  result: OutcomeResult;
  tracking_state: ShadowTrackingState;
  no_entry_reason: string | null;
  censored_reason: string | null;
  r_multiple: string | null;
  r_multiple_reason: string | null;
  r_ex_funding: string | null;
  /** `signal_outcomes.meta.excursions` verbatim -- unit is always `price`, never trimmed. */
  excursions: Record<string, unknown>;
  purpose: string;
  /** Always present in the schema; `null` unless `?include=envelope`. */
  supporting_features: Record<string, unknown> | null;
}

export interface LabSignalsPage {
  items: SignalListItemOut[];
  next_cursor: string | null;
}
