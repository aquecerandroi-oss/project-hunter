/**
 * Fixtures mirroring the real T2.6 contract examples
 * (`apps/api/tests/integration/analysis_fixtures.py`'s defaults, and the
 * real `decomposition()`/`explain()` wire shapes from
 * `packages/indicators/hunter_indicators/opportunity/{model,explanation}.py`)
 * -- never invented shapes, per CLAUDE.md.
 */
import type { AnomalyOut } from "@/lib/api/anomalies-types";
import type { OpportunityAnomalyOut, OpportunityDetailOut, OpportunitySummaryOut } from "@/lib/api/opportunities-types";
import type { RadarItemOut } from "@/lib/api/radar-types";
import type { RegimeOut } from "@/lib/api/regime-types";

export function makeRadarItem(overrides: Partial<RadarItemOut> = {}): RadarItemOut {
  return {
    opportunity_id: "11111111-1111-1111-1111-111111111111",
    market_id: "22222222-2222-2222-2222-222222222222",
    exchange: "binance",
    symbol: "BTCUSDT",
    market_type: "perpetual",
    direction: "long",
    score: "55.00",
    confidence: "0.5000",
    status: "WATCHING",
    stage: "NONE",
    regime: "SIDEWAYS",
    change: "0",
    first_seen_at: "2026-09-05T12:00:00Z",
    last_updated_at: "2026-09-06T08:00:00Z",
    in_position: null,
    risk_blocked: null,
    risk_blocked_reason: null,
    ...overrides,
  };
}

export function makeOpportunitySummary(overrides: Partial<OpportunitySummaryOut> = {}): OpportunitySummaryOut {
  return {
    id: "11111111-1111-1111-1111-111111111111",
    market_id: "22222222-2222-2222-2222-222222222222",
    exchange: "binance",
    symbol: "BTCUSDT",
    market_type: "perpetual",
    direction: "long",
    score: "55.00",
    confidence: "0.5000",
    status: "WATCHING",
    stage: "NONE",
    regime: "SIDEWAYS",
    weights_version: "v2",
    first_seen_at: "2026-09-05T12:00:00Z",
    last_updated_at: "2026-09-06T08:00:00Z",
    in_position: null,
    risk_blocked: null,
    ...overrides,
  };
}

/** The exact `decomposition()` wire shape (`opportunity/model.py:268`). */
export function makeDecomposition(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    scorer_version: "scorer_v1",
    profile_version: "profile_v1",
    weights_version: "v2",
    versions: { scorer: "scorer_v1", components: "components_v1" },
    observation_ts: "2026-09-06T08:00:00Z",
    eligible: true,
    reason: null,
    score: "70.0000",
    confidence: "0.6500",
    direction: "long",
    direction_reason: null,
    agreement: "0.8000",
    early_movement: { e: 1, magnitude: "2.5000", contribution: "2.5000", stage: "EARLY", stage_direction: "long", reason: null },
    components: [
      {
        name: "momentum",
        kind: "mad",
        transform: "mad_piecewise_v1",
        weight: "0.2000",
        raw: "10.0000",
        normalized: "80.0000",
        contribution: "16.0000",
        confidence: "0.9000",
        direction: "long",
        expected: 4,
        used: 4,
        available: true,
        reason: null,
        inputs: [
          {
            feature: "momentum_15m",
            available: true,
            value: "0.0123",
            baseline: "0.0050",
            scale: "0.0020",
            deviation: "3.6500",
            severity: "80.0000",
            maturity: "0.9000",
            direction: "long",
            baseline_id: "33333333-3333-3333-3333-333333333333",
            reason: null,
          },
        ],
        not_implemented: {},
        detail: {},
      },
      {
        name: "derivatives",
        kind: "mad",
        transform: "mad_piecewise_v1",
        weight: "0.1000",
        raw: null,
        normalized: null,
        contribution: "0.0000",
        confidence: "0.0000",
        direction: "neutral",
        expected: 2,
        used: 0,
        available: false,
        reason: "no_usable_input",
        inputs: [],
        not_implemented: {},
        detail: {},
      },
    ],
    baseline_ids: ["33333333-3333-3333-3333-333333333333"],
    ...overrides,
  };
}

/** The exact `explain()` wire shape (`opportunity/explanation.py:217`). */
export function makeExplanation(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    version: "explanation_v1",
    idioma: "pt-BR",
    gerado_de: { scorer: "scorer_v1", components: "components_v1", weights_version: "v2", observation_ts: "2026-09-06T08:00:00Z" },
    resumo: "Score 70,00 de 100, confiança 0,6500, direção long.",
    frases: [
      { codigo: "score", texto: "Score 70,00 de 100, confiança 0,6500, direção long.", valores: {} },
      { codigo: "componente", texto: "Momentum: 80,0000 de 100 (peso 0,20) contribuiu 16,0000 pontos.", valores: {} },
    ],
    componentes: [{ nome: "momentum", rotulo: "Momentum", normalizado: "80.0000", peso: "0.2000", contribuicao: "16.0000", disponivel: true, motivo: null }],
    early_movement: { e: 1, magnitude: "2.5000", contribution: "2.5000", stage: "EARLY", stage_direction: "long", reason: null },
    ...overrides,
  };
}

/** The real envelope shape (`opportunity/envelope.py:37`, `FeatureVector.as_wire()`). */
export function makeFeatureSnapshot(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    as_of: "2026-09-06T08:00:00Z",
    vector: {
      exchange: "binance",
      symbol: "BTCUSDT",
      ts: "2026-09-06T08:00:00Z",
      feature_set_version: "v1",
      quality_policy_version: "quality_v1",
      values: {
        atr_14_pct: { value: "0.0123", quality: "ok", reason: null, inputs: [] },
        relative_volume_1h: { value: null, quality: "unavailable", reason: "warmup", inputs: [] },
      },
      provenance: {},
    },
    baseline_ids: ["33333333-3333-3333-3333-333333333333"],
    regime_id: null,
    regime: null,
    regime_stale: false,
    versions: { scorer: "scorer_v1" },
    ...overrides,
  };
}

export function makeOpportunityAnomaly(overrides: Partial<OpportunityAnomalyOut> = {}): OpportunityAnomalyOut {
  return {
    id: "44444444-4444-4444-4444-444444444444",
    type: "VOLUME_SPIKE",
    severity: "70.00",
    confidence: "0.8000",
    status: "active",
    evaluation_state: "ok",
    detected_at: "2026-09-06T07:00:00Z",
    ...overrides,
  };
}

export function makeAnomaly(overrides: Partial<AnomalyOut> = {}): AnomalyOut {
  return {
    id: "44444444-4444-4444-4444-444444444444",
    market_id: "22222222-2222-2222-2222-222222222222",
    exchange: "binance",
    symbol: "BTCUSDT",
    type: "VOLUME_SPIKE",
    severity: "70.00",
    confidence: "0.8000",
    status: "active",
    evaluation_state: "ok",
    detected_at: "2026-09-06T07:00:00Z",
    feature_snapshot: {},
    ...overrides,
  };
}

export function makeRegime(overrides: Partial<RegimeOut> = {}): RegimeOut {
  return {
    id: "55555555-5555-5555-5555-555555555555",
    scope: "global",
    regime: "SIDEWAYS",
    confidence: "0.7500",
    start_time: "2026-09-06T00:00:00Z",
    end_time: null,
    classifier_version: "classifier_v1",
    supporting_features: {},
    is_stale: false,
    ...overrides,
  };
}

export function makeOpportunityDetail(overrides: Partial<OpportunityDetailOut> = {}): OpportunityDetailOut {
  return {
    id: "11111111-1111-1111-1111-111111111111",
    market_id: "22222222-2222-2222-2222-222222222222",
    exchange: "binance",
    symbol: "BTCUSDT",
    market_type: "perpetual",
    direction: "long",
    score: "70.00",
    confidence: "0.6500",
    status: "HOT",
    stage: "EARLY",
    regime: "SIDEWAYS",
    weights_version: "v2",
    first_seen_at: "2026-09-05T12:00:00Z",
    last_updated_at: "2026-09-06T08:00:00Z",
    in_position: null,
    risk_blocked: null,
    peak_score: "75.00",
    decomposition: makeDecomposition(),
    explanation: makeExplanation(),
    feature_snapshot: makeFeatureSnapshot(),
    baseline_ids: ["33333333-3333-3333-3333-333333333333"],
    regime_id: "55555555-5555-5555-5555-555555555555",
    below_40_since: null,
    expired_at: null,
    anomalies: [makeOpportunityAnomaly()],
    history: [
      { ts: "2026-09-06T08:00:00Z", score: "70.00", confidence: "0.6500", status: "HOT", stage: "EARLY", decomposition: {}, envelope: null },
      { ts: "2026-09-06T07:00:00Z", score: "65.00", confidence: "0.6000", status: "WATCHING", stage: "NONE", decomposition: {}, envelope: null },
    ],
    risk_blocked_reason: null,
    ...overrides,
  };
}
