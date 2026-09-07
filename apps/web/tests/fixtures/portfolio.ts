import type {
  BrlDecomposition,
  EquityCurvePoint,
  FxObservation,
  KillSwitchDetail,
  PortfolioAnchor,
  PortfolioRiskState,
  PortfolioSummary,
} from "@/lib/api/portfolio-types";

/**
 * Fixtures for the T3.8b wallet screen. Shapes mirror the real Pydantic
 * schemas (`apps/api/hunter_api/schemas/{portfolio,portfolio_lists,risk}.py`)
 * -- every Decimal field is a plain decimal string, never a `number`.
 */

export function makeFxObservation(overrides: Partial<FxObservation> = {}): FxObservation {
  return {
    id: "fx-1",
    pair: "USDTBRL",
    source: "binance.spot.ticker",
    rate: "5.4000000000",
    observed_at: "2026-09-07T12:00:00Z",
    available_at: "2026-09-07T12:00:05Z",
    ...overrides,
  };
}

export function makeAnchor(overrides: Partial<PortfolioAnchor> = {}): PortfolioAnchor {
  return {
    portfolio_id: "wallet-1",
    origin_currency: "BRL",
    origin_amount: "100000.0000000000",
    operating_currency: "USDT",
    credited_amount: "18518.5185180000",
    rate: "5.4000000000",
    conversion_residual: "0.0000000200",
    rounding_policy: "floor_10dp_v1",
    anchored_at: "2026-09-01T13:00:00Z",
    fx_observation: makeFxObservation({ id: "fx-opening", observed_at: "2026-09-01T12:59:50Z" }),
    ...overrides,
  };
}

export function makeBrl(overrides: Partial<BrlDecomposition> = {}): BrlDecomposition {
  return {
    opening_brl: "100000.0000000000",
    operational_brl: "540.0000000000",
    currency_brl: "185.1851850000",
    equity_brl: "100725.1851850000",
    total_brl: "725.1851850000",
    opening_rate: "5.4000000000",
    current_rate: "5.4100000000",
    fx_observation: makeFxObservation(),
    ...overrides,
  };
}

export function makeRiskState(overrides: Partial<PortfolioRiskState> = {}): PortfolioRiskState {
  return {
    trading_day: "2026-09-07",
    trading_day_timezone: "America/Sao_Paulo",
    trading_day_start_utc: "2026-09-07T03:00:00Z",
    equity_day_start: "18600.0000000000",
    day_reference_observed_at: "2026-09-07T03:00:05Z",
    peak_equity: "18700.0000000000",
    peak_equity_observed_at: "2026-09-07T10:00:00Z",
    peak_sampling_interval_s: 60,
    daily_loss_pct: "-0.0050000000",
    drawdown_pct: "-0.0100000000",
    kill_switch: {
      effective: "ACTIVE",
      blocks_entries: false,
      scopes: { system: "ACTIVE", organization: "ACTIVE", portfolio: "ACTIVE" },
      reason: null,
      last_transition: null,
    },
    ...overrides,
  };
}

export function makeSummary(overrides: Partial<PortfolioSummary> = {}): PortfolioSummary {
  return {
    id: "wallet-1",
    organization_id: "org-1",
    workspace_id: "ws-1",
    name: "Carteira principal",
    type: "paper",
    status: "active",
    base_currency: "USDT",
    as_of: "2026-09-07T12:00:10Z",
    cash: "10000.0000000000",
    equity: "18650.5000000000",
    exposure_notional: "8650.5000000000",
    unrealized_pnl: "125.5000000000",
    realized_pnl_cum: "525.0000000000",
    open_position_count: 2,
    reserved_cash: "500.0000000000",
    reserved_notional: "1200.0000000000",
    reserved_risk: "46.6000000000",
    marks_complete: true,
    unavailable: [],
    brl: makeBrl(),
    brl_unavailable_reason: null,
    brl_unavailable_detail: null,
    risk_state: makeRiskState(),
    ...overrides,
  };
}

export function makeKillSwitch(overrides: Partial<KillSwitchDetail> = {}): KillSwitchDetail {
  return {
    portfolio_id: "wallet-1",
    effective: "ACTIVE",
    blocks_entries: false,
    scopes: { system: "ACTIVE", organization: "ACTIVE", portfolio: "ACTIVE" },
    reason: null,
    daily_reference: {
      trading_day: "2026-09-07",
      trading_day_timezone: "America/Sao_Paulo",
      trading_day_start_utc: "2026-09-07T03:00:00Z",
      equity_day_start: "18600.0000000000",
      observed_at: "2026-09-07T03:00:05Z",
      available: true,
    },
    peak: { equity: "18700.0000000000", observed_at: "2026-09-07T10:00:00Z", sampling_interval_s: 60 },
    last_transition: null,
    ...overrides,
  };
}

export function makeEquityPoint(overrides: Partial<EquityCurvePoint> = {}): EquityCurvePoint {
  return {
    ts: "2026-09-07T11:00:00Z",
    resolution: "1h",
    cash: "10000.0000000000",
    equity: "18650.5000000000",
    exposure_notional: "8650.5000000000",
    exposure_pct: "0.4640000000",
    unrealized_pnl: "125.5000000000",
    realized_pnl_cum: "525.0000000000",
    peak_equity: "18700.0000000000",
    drawdown_pct: "-0.0100000000",
    open_positions: 2,
    fx_observation_id: "fx-1",
    brl_equity: "100916.4550000000",
    brl_unavailable_reason: null,
    ...overrides,
  };
}
