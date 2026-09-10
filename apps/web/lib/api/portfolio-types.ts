/**
 * TypeScript aliases onto the OpenAPI-generated `components["schemas"]` for
 * the T3.8a wallet contract (`apps/api/hunter_api/routers/{portfolio,risk}.py`,
 * `schemas/{portfolio,portfolio_lists,risk}.py`) -- same pattern as
 * `lib/api/radar-types.ts`. Every Decimal field the API sends stays a
 * `string` here (never `number` -- CLAUDE.md: money/PnL is never `float`).
 */
import type { components } from "@hunter/shared-types/api";

export type PortfolioListItem = components["schemas"]["PortfolioListItemOut"];
export type PortfolioType = components["schemas"]["PortfolioType"];
export type PortfolioStatus = components["schemas"]["PortfolioStatus"];
export type PositionStatus = components["schemas"]["PositionStatus"];
export type OrderSide = components["schemas"]["OrderSide"];
export type OrderType = components["schemas"]["OrderType"];
export type OrderPurpose = components["schemas"]["OrderPurpose"];
export type OrderStatus = components["schemas"]["OrderStatus"];
export type ExecutionMode = components["schemas"]["ExecutionMode"];
export type ExitReason = components["schemas"]["ExitReason"];

export type FxObservation = components["schemas"]["FxObservationOut"];
export type PortfolioAnchor = components["schemas"]["AnchorOut"];
export type BrlDecomposition = components["schemas"]["BrlDecompositionOut"];
export type PortfolioRiskState = components["schemas"]["PortfolioRiskStateOut"];
export type KillSwitchSummary = components["schemas"]["KillSwitchSummaryOut"];
export type PortfolioSummary = components["schemas"]["PortfolioSummaryOut"];

export type EquityCurvePoint = components["schemas"]["EquityCurvePointOut"];
/** One `positions` row. Empty today -- no writer exists yet (T3.4/T3.5). */
export type PositionRow = components["schemas"]["PositionOut"];
/** One `orders` row. Empty today -- no writer exists yet (T3.4/T3.5). */
export type OrderRow = components["schemas"]["OrderOut"];
/** One `trades` row. Empty today -- no writer exists yet (T3.4/T3.5). */
export type PortfolioTradeRow = components["schemas"]["PortfolioTradeOut"];

export type KillSwitchStateValue = components["schemas"]["KillSwitchState"];
export type ScopeStates = components["schemas"]["ScopeStatesOut"];
export type KillSwitchTransition = components["schemas"]["TransitionOut"];
export type DailyReference = components["schemas"]["DailyReferenceOut"];
export type Peak = components["schemas"]["PeakOut"];
/** `GET .../risk/kill-switch` -- richer than `KillSwitchSummary` embedded in
 * `PortfolioSummary`: it derives `blocks_entries` from the daily reference's
 * own availability too (`routers/risk.py::read_kill_switch`), which the
 * summary's own `_kill_switch_summary` does not. This is the source of truth
 * for whether entries are actually blocked right now. */
export type KillSwitchDetail = components["schemas"]["KillSwitchOut"];

/**
 * `RiskLimitsPresetOut` (`apps/api/hunter_api/schemas/risk_limits.py`) plus
 * `diverged_from_engine` (T3.69b/T3.72d), added here by hand: the generated
 * `packages/shared-types/src/generated/api.d.ts` at this HEAD (`718c347`)
 * still predates that field -- regenerating it runs `uv run python
 * infra/scripts/dump_openapi.py` (`pnpm gen:types`) and writes outside
 * `apps/web/**`, out of this task's scope. Drop this intersection once the
 * generated type carries the field itself.
 */
export type RiskLimitsPreset = components["schemas"]["RiskLimitsPresetOut"] & {
  /** True when the wallet's stored profile is not byte-for-byte `PAPER_V1`
   * (or does not validate as a profile at all) -- the execution-worker
   * admits nothing in either case (`risk_profile_diverged`/`risk_profile_invalid`,
   * `services/execution-worker/hunter_execution_worker/risk_profile.py`). */
  diverged_from_engine: boolean;
};

/**
 * `GET .../risk/limits` (T3.72) -- the numeric `paper_v1` preset the "Nova
 * ordem paper" form needs (`max_stop_distance_pct`), plus the wallet's
 * current usage against it. `preset` is overridden with the hand-augmented
 * `RiskLimitsPreset` above (`components["schemas"]["RiskLimitsOut"]["preset"]`
 * on its own still points at the stale generated `RiskLimitsPresetOut`,
 * unaware of this file's own alias by the same name) -- everything else is
 * exactly the generated shape.
 */
export type RiskLimits = Omit<components["schemas"]["RiskLimitsOut"], "preset"> & {
  preset: RiskLimitsPreset;
};

export interface AsOfPage<T> {
  as_of: string;
  items: T[];
  next_cursor?: string | null;
}

export interface CursorPage<T> {
  items: T[];
  next_cursor?: string | null;
}
