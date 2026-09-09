/**
 * The real envelope of one `trendline_breakout v1` decision, copied verbatim
 * (SQL, values only) from the VPS (read-only, `repeatable read read only`)
 * -- brief T3.49's own instruction, not invented:
 *
 * ```
 * ssh hunter-vps "docker exec -i hunter-postgres-1 psql -U hunter -d hunter -tAc \
 *   \"begin transaction isolation level repeatable read read only; \
 *     select a.supporting_features::text from signal_outcomes o \
 *     join agent_signals a on a.id = o.signal_id \
 *     where o.meta->>'cohort' = 'replay:d78c14d1-b4c5-424a-8f31-a43100744bb4' \
 *     order by (o.meta->'entry_plan'->>'source_bar_close')::timestamptz limit 1; commit;\""
 * ```
 *
 * DOGEUSDT, `2026-08-19 23:45:00+00` -- the same row `.claude/state/notes-T3.34c.md`
 * §8 already shows flattened; this is the untruncated JSON as it sits in
 * `agent_signals.supporting_features`. The matching row/plan fields (stop,
 * targets, virtual entry/exit, exchange) were read with a second, equally
 * read-only query joining `signal_outcomes`/`agent_signals`/`markets`/`exchanges`.
 */
export function exampleTrendlineSupportingFeatures(): Record<string, unknown> {
  return {
    atr: {
      seed: "0.0001164285714285714285714285714",
      value: "0.0006234504938842306401178667624",
      method: "wilder_v1",
      origin: "rolling_window_v1",
      period: "14",
      percent: "0.008294977300215947846166401841",
      bars_used: "97",
      timeframe: "15m",
      window_end: "2026-08-19T23:45:00Z",
      seed_anchor: "2026-08-19T03:00:00Z",
      window_start: "2026-08-18T23:30:00Z",
    },
    cohort: "replay:d78c14d1-b4c5-424a-8f31-a43100744bb4",
    purpose: "research_only",
    eligible: true,
    features: [
      { name: "open_15m", value: "0.07484", window: null, available: true, source_ts: "2026-08-19T23:30:00Z", unavailable_reason: null },
      { name: "high_15m", value: "0.07528", window: null, available: true, source_ts: null, unavailable_reason: null },
      { name: "low_15m", value: "0.07462", window: null, available: true, source_ts: null, unavailable_reason: null },
      { name: "volume_15m", value: "87097332", window: null, available: true, source_ts: null, unavailable_reason: null },
      { name: "close_15m", value: "0.07516", window: null, available: true, source_ts: "2026-08-19T23:45:00Z", unavailable_reason: null },
      { name: "relative_volume_15m", value: "2.493235767252546355853982023", window: "96", available: true, source_ts: null, unavailable_reason: null },
      { name: "volume_median_15m", value: "35722817", window: "96", available: true, source_ts: null, unavailable_reason: null },
      { name: "atr_pct_15m", value: "0.008294977300215947846166401841", window: "97", available: true, source_ts: null, unavailable_reason: null },
      { name: "line_kind", value: "support", window: null, available: true, source_ts: null, unavailable_reason: null },
      { name: "line_id", value: "03422055d14efe64", window: null, available: true, source_ts: null, unavailable_reason: null },
      { name: "line_slope_per_bar", value: "0.0001217142857142857142857142857", window: null, available: true, source_ts: null, unavailable_reason: null },
      { name: "line_touches", value: "3", window: null, available: true, source_ts: null, unavailable_reason: null },
      { name: "line_violations", value: "0", window: null, available: true, source_ts: null, unavailable_reason: null },
      { name: "line_first_idx", value: "57", window: null, available: true, source_ts: null, unavailable_reason: null },
      { name: "line_last_idx", value: "92", window: null, available: true, source_ts: null, unavailable_reason: null },
      { name: "line_valid_from_idx", value: "95", window: null, available: true, source_ts: null, unavailable_reason: null },
      { name: "line_price_at_decision", value: "0.07470514285714285714285714286", window: null, available: true, source_ts: null, unavailable_reason: null },
      { name: "event_kind", value: "bounce", window: null, available: true, source_ts: null, unavailable_reason: null },
      { name: "event_distance_atr", value: "0.7295685515803986024445902112", window: null, available: true, source_ts: null, unavailable_reason: null },
      { name: "pivot_low_price", value: "0.07434", window: null, available: true, source_ts: null, unavailable_reason: null },
      { name: "pivot_low_idx", value: "92", window: null, available: true, source_ts: null, unavailable_reason: null },
      { name: "pattern_bars", value: "96", window: null, available: true, source_ts: null, unavailable_reason: null },
      { name: "pattern_pivots", value: "13", window: null, available: true, source_ts: null, unavailable_reason: null },
      { name: "pattern_lines", value: "2", window: null, available: true, source_ts: null, unavailable_reason: null },
      { name: "pattern_retired_lines", value: "0", window: null, available: true, source_ts: null, unavailable_reason: null },
      {
        name: "pattern_params",
        value:
          '{"angle_bucket_atr":"0.1","atr_period":"14","bounce_atr":"0.5","bounce_bars":"3","break_atr":"0.5","level_bucket_atr":"0.5","max_anchors":"20","max_channels":"3","max_lines":"6","min_swing_atr":"1","min_touches":"3","parallel_tol":"0.05","pivot_k":"3","retest_bars":"10","retire_after_break":true,"rvol_min":null,"tolerance_atr":"0.25"}',
        window: null,
        available: true,
        source_ts: null,
        unavailable_reason: null,
      },
      { name: "channel_width_atr", value: null, window: null, available: false, source_ts: null, unavailable_reason: "no_channel" },
    ],
    timeframe: "15m",
    provenance: {
      code_ref: "hunter_core.strategies.trendline_breakout_v1@sha256:7b83a1ff07946fa743d12c9d098f15b538c2e2b19f5269363203ee0671e19648",
      producer: "strategy-worker.shadow",
      regime_id: null,
      funding_ts: "2026-08-19T16:00:00.004000Z",
      params_hash: "f2e8017c7251e22fde74c70a6f36ac4f65674cfdad536d18ddf6f31e7b976e4a",
      regime_reason: "no_regime_asof",
      funding_reason: null,
      funding_source: "durable",
      bars_in_context: "1560",
      newest_bar_open: "2026-08-19T23:44:00Z",
      open_interest_ts: null,
      available_through: "2026-09-08T05:09:09.656726Z",
      strategy_version_id: "01a08323-7c1e-7b83-8527-553a329e4c32",
      open_interest_reason: "no_data",
      open_interest_source: null,
      eligibility_observed_at: "2026-09-08T22:33:17.167566Z",
    },
    decision_at: "2026-08-19T23:45:02Z",
    strategy_key: "trendline_breakout_v1",
    assumed_costs: { fee_bps: "4", spread_bps: "2", slippage_bps: "5", max_entry_delay_s: "120" },
    params_format: "1",
    observation_ts: "2026-08-19T23:45:00Z",
    strategy_version: "v1",
    confidence_method: "constant_uncalibrated_v1",
    eligibility_reason: null,
  };
}

/**
 * The matching row's plan/outcome fields (same DOGEUSDT decision, real
 * values), read from `agent_signals`/`signal_outcomes`/`markets`/`exchanges`
 * with a second read-only VPS query -- `stop`/`target1` from `agent_signals`,
 * `virtual_entry`/`entry_ts`/`exit_price`/`exit_ts`/`result` from
 * `signal_outcomes`, `exchange`/`symbol` from `markets`/`exchanges`.
 */
export const EXAMPLE_TRENDLINE_OPERATION = {
  exchange: "binance",
  symbol: "DOGEUSDT",
  decisionBarClose: "2026-08-19T23:45:00Z",
  stop: "0.0739130990",
  target1: "0.0776538020",
  referencePrice: "0.07516",
  virtualEntry: "0.0751150420",
  entryTs: "2026-08-19T23:46:00Z",
  exitPrice: "0.0745852220",
  exitTs: "2026-08-20T04:30:00Z",
  result: "invalidated" as const,
  trackingState: "terminal" as const,
};
