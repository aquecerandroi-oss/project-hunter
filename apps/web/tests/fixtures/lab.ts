import type { LabSummaryOut, SignalListItemOut, VersionSummaryOut } from "@/lib/api/lab-types";

/**
 * Fixtures copied from the real example in `.claude/state/contract-S3-lab.md`
 * (SQL run against `docker-postgres-1`, `momentum`/`v2`, `window=all`, S3a) --
 * not invented numbers. `makeVersionSummary`/`makeSignal` below layer
 * `overrides` on top for the handful of tests that need a different shape
 * (e.g. a `null` metric, a different `tracking_state`).
 */
export function exampleVersionSummary(): VersionSummaryOut {
  return {
    strategy_version_id: "098b060c-cdc0-46a6-b88b-70d4a5472b97",
    strategy_key: "momentum",
    version: "v2",
    code_ref: "hunter_core.strategies.momentum_v1@sha256:c012f75c...",
    status: "active",
    activated_at: "2026-09-06T02:08:13.332014Z",
    deprecated_at: null,
    counts: {
      decisions: null,
      decisions_reason: "evaluation_state_not_persisted",
      signals_emitted: 18,
      pending_entry: 4,
      entered: 11,
      no_entry: { total: 3, by_reason: { "late:delay": 3, "late:missed_open": 0, "late:unconfirmed": 0, geometry: 0 } },
      active: 2,
      terminal: { total: 9, by_result: { target: 2, stop: 2, expired: 0, invalidated: 5 } },
      censored: { total: 0, by_reason: {} },
      funding_not_settleable: 0,
    },
    metrics: {
      target_rate_among_resolved_touches: { value: "0.5000", reason: null },
      net_profit_rate: { value: "0.2222", reason: null },
      hypothetical_net_expectancy_r: { value: "-0.4362", reason: null },
      profit_factor: { value: "0.2461", reason: null, sum_positive: "1.2809", sum_negative_abs: "5.2068", sample_size: 9 },
      sum_of_hypothetical_r: { value: "-3.9258", reason: null, count: 9, ordered_by: "exit_ts" },
    },
    r_ex_funding: {
      net_profit_rate: { value: "0.2222", reason: null },
      hypothetical_net_expectancy_r: { value: "-0.4361", reason: null },
      profit_factor: { value: "0.2462", reason: null, sum_positive: "1.2816", sum_negative_abs: "5.2059", sample_size: 9 },
      sum_of_hypothetical_r: { value: "-3.9251", reason: null, count: 9, ordered_by: "exit_ts" },
      coverage: { evaluable_outcomes: 9, r_net_evaluable_outcomes: 9 },
    },
    portfolio_pnl: null,
    portfolio_pnl_reason: "not_applicable",
    portfolio_max_drawdown: null,
    portfolio_max_drawdown_reason: "not_applicable",
    maturity: { evaluable_outcomes: 9, distinct_days: 1, inconclusive: true },
    coverage: {
      markets_with_signals: 18,
      distinct_days: 1,
      note: "counts markets/days that produced at least one signal — evaluations that never triggered are not observable",
      assumed_costs: { assumed_spread_bps: "2", slippage_bps: "5", fee_bps: "4", max_entry_delay_s: 120 },
    },
  };
}

export function makeVersionSummary(overrides: Partial<VersionSummaryOut> = {}): VersionSummaryOut {
  return { ...exampleVersionSummary(), ...overrides };
}

export function exampleSummary(overrides: Partial<LabSummaryOut> = {}): LabSummaryOut {
  return {
    as_of: "2026-09-06T12:00:00Z",
    window: "all",
    cohort: "prospective",
    label: "SOMBRA — hipotético, sem capital, custos assumidos",
    versions: [exampleVersionSummary()],
    ...overrides,
  };
}

export function exampleSignal(): SignalListItemOut {
  return {
    signal_id: "07984643-a085-5ec1-b38b-ea0c325aa758",
    strategy_version_id: "098b060c-cdc0-46a6-b88b-70d4a5472b97",
    market: "AAAAUSDT",
    cohort: "prospective",
    decision_at: "2026-09-06T00:25:01.939152Z",
    source_bar_close: "2026-09-06T00:25:00Z",
    reference_price: "27453.1200000000",
    stop: "27100.0000000000",
    target1: "27950.0000000000",
    entry_plan: {
      source_bar_close: "2026-09-06T00:25:00Z",
      decision_at: "2026-09-06T00:25:01.939152Z",
      entry_bar_open: "2026-09-06T00:26:00Z",
      delay_s: 60,
      max_entry_delay_s: 120,
      late_reason: null,
    },
    virtual_entry: "27460.0000000000",
    entry_ts: "2026-09-06T00:26:00Z",
    exit_price: "27100.0000000000",
    exit_ts: "2026-09-06T03:41:00Z",
    result: "stop",
    tracking_state: "terminal",
    no_entry_reason: null,
    censored_reason: null,
    r_multiple: "-1.0421",
    r_multiple_reason: null,
    r_ex_funding: "-1.0400",
    excursions: {
      unit: "price",
      method: "ohlc_complete_bars_v1",
      available: true,
      coverage: { bars_known: 12, bars_total: 15 },
      mfe: null,
      mae: "0.8000",
      mfe_ts: null,
      mae_ts: null,
      mfe_bar: null,
      mae_bar: "2026-09-06T02:10:00Z",
      mfe_complete_bars: "0",
      mae_complete_bars: "0.8000",
      bounds: { mfe: [0, 4.2], mae: [0.8, 0.8] },
      bar_windows: { first_open: "2026-09-06T00:26:00Z", last_open: "2026-09-06T03:40:00Z", exit_bar_open: "2026-09-06T03:41:00Z" },
      ambiguous: true,
      initial_risk: "353.1200000000",
      reference_price: "27453.1200000000",
    },
    purpose: "research_only",
    supporting_features: null,
  };
}

export function makeSignal(overrides: Partial<SignalListItemOut> = {}): SignalListItemOut {
  return { ...exampleSignal(), ...overrides };
}
