/**
 * Fixture mirroring the real `GET /api/v1/radar/coverage` contract
 * (`apps/api/hunter_api/schemas/radar_coverage.py`, T3.46) -- never an
 * invented shape, per CLAUDE.md. Defaults are the actual T3.46 numbers
 * (`.claude/state/notes-T3.46.md`): 25/217 markets, ~8% baselines usable,
 * max score ever 38.33, four of twelve detectors producing.
 */
import type { RadarCoverageOut, RadarDetectorOut } from "@/lib/api/radar-coverage-types";

export function makeRadarDetector(overrides: Partial<RadarDetectorOut> = {}): RadarDetectorOut {
  return {
    type: "VOLUME_SPIKE",
    rows_31d: 575,
    disarmed_reason: null,
    ...overrides,
  };
}

export function makeRadarCoverage(overrides: Partial<RadarCoverageOut> = {}): RadarCoverageOut {
  return {
    markets_monitored: 217,
    markets_with_anomaly: 25,
    baselines_usable: 9029,
    baselines_under_construction: 102597,
    bootstrap_pointer: "bootstrapping 1000FLOKIUSDT (4/200)",
    baseline_gate_v2_pct: "4.28",
    detectors: [
      makeRadarDetector({ type: "VOLUME_SPIKE", rows_31d: 575 }),
      makeRadarDetector({ type: "MOMENTUM_SHIFT", rows_31d: 335 }),
      makeRadarDetector({ type: "PRICE_ACCELERATION", rows_31d: 329 }),
      makeRadarDetector({ type: "VOLATILITY_EXPANSION", rows_31d: 48 }),
      makeRadarDetector({
        type: "CROSS_EXCHANGE_DIVERGENCE",
        rows_31d: 0,
        disarmed_reason: "single_exchange_until_m1b",
      }),
      makeRadarDetector({ type: "FUNDING_ANOMALY", rows_31d: 0, disarmed_reason: "funding_unavailable" }),
      makeRadarDetector({
        type: "LIQUIDATION_CLUSTER",
        rows_31d: 0,
        disarmed_reason: "feature_not_implemented",
      }),
      makeRadarDetector({ type: "ORDERBOOK_IMBALANCE", rows_31d: 0, disarmed_reason: null }),
      makeRadarDetector({ type: "OPEN_INTEREST_SPIKE", rows_31d: 0, disarmed_reason: null }),
      makeRadarDetector({ type: "TRADE_VELOCITY_SPIKE", rows_31d: 0, disarmed_reason: null }),
      makeRadarDetector({ type: "SOCIAL_SPIKE", rows_31d: 0, disarmed_reason: null }),
      makeRadarDetector({ type: "WHALE_ACTIVITY", rows_31d: 0, disarmed_reason: null }),
    ],
    max_score_ever: "38.33",
    first_anomaly_at: "2026-09-07T02:24:01Z",
    as_of: "2026-09-08T22:37:00Z",
    ...overrides,
  };
}
