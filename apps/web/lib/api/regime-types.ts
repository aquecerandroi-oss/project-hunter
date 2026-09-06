/** Aliases onto the T2.6 regime contract (`apps/api/hunter_api/routers/regime.py`, `schemas/regime.py`). */
import type { components } from "@hunter/shared-types/api";

export type RegimeOut = components["schemas"]["RegimeOut"];
export type RegimeCurrentOut = components["schemas"]["RegimeCurrentOut"];
export type RegimeHistoryPage = components["schemas"]["RegimeHistoryPage"];
export type RegimeScopeValue = components["schemas"]["RegimeScope"];

export const REGIME_SCOPE_VALUES: RegimeScopeValue[] = ["global", "btc"];
export const REGIME_SCOPE_LABELS: Record<RegimeScopeValue, string> = {
  global: "Global",
  btc: "BTC",
};

export interface RegimeHistoryParams {
  scope?: RegimeScopeValue;
  limit?: number;
  cursor?: string;
}
