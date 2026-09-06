/** Aliases onto the T2.6 anomalies contract (`apps/api/hunter_api/routers/anomalies.py`, `schemas/anomalies.py`). */
import type { components } from "@hunter/shared-types/api";

export type AnomalyOut = components["schemas"]["AnomalyOut"];
export type AnomalyPage = components["schemas"]["AnomalyPage"];
export type AnomalyTypeValue = components["schemas"]["AnomalyType"];
export type AnomalyStatusValue = components["schemas"]["AnomalyStatus"];
export type AnomalyEvaluationStateValue = components["schemas"]["AnomalyEvaluationState"];

export const ANOMALY_STATUS_VALUES: AnomalyStatusValue[] = ["active", "resolved", "expired"];
export const ANOMALY_EVALUATION_STATE_VALUES: AnomalyEvaluationStateValue[] = ["ok", "stale", "unknown"];

export interface AnomaliesParams {
  window_hours?: number;
  type?: AnomalyTypeValue;
  status?: AnomalyStatusValue;
  market_id?: string;
  min_severity?: string;
  limit?: number;
  cursor?: string;
}

/** `MAX_WINDOW_HOURS` (`routers/anomalies.py`) -- 30 days, the widest window the API accepts. */
export const MAX_ANOMALY_WINDOW_HOURS = 24 * 30;
/** `DEFAULT_WINDOW_HOURS` (`routers/anomalies.py`) -- the market-detail timeline's default. */
export const DEFAULT_ANOMALY_WINDOW_HOURS = 24;

/**
 * The Radar table's "anomalias ativas" column source (`components/radar/anomaly-count-cell.tsx`):
 * one `GET /api/v1/anomalies?status=active&window_hours=720` read grouped by
 * `market_id`, carrying its OWN `as_of` -- never conflated with the radar's
 * own query time (Astra's T2.7 diff review, must-fix 3). `unavailable` is
 * the read itself failing; `truncated` is `next_cursor !== null` on that
 * read (a real anomaly can then be missing from `byMarket` for a market not
 * covered by the truncated page, distinct from "no anomaly at all").
 */
export interface AnomaliesAggregate {
  byMarket: Record<string, { type: AnomalyTypeValue }[]>;
  unavailable: boolean;
  truncated: boolean;
  asOf: string;
}

/** Builds the aggregate from a real `AnomalyPage` -- shared by the initial SSR fetch and the client reconciliation Server Action so the two never drift. */
export function buildAnomaliesAggregate(page: AnomalyPage): AnomaliesAggregate {
  const byMarket: Record<string, { type: AnomalyTypeValue }[]> = {};
  for (const item of page.items) {
    (byMarket[item.market_id] ??= []).push({ type: item.type });
  }
  return { byMarket, unavailable: false, truncated: page.next_cursor !== null, asOf: page.as_of };
}

export function unavailableAnomaliesAggregate(): AnomaliesAggregate {
  return { byMarket: {}, unavailable: true, truncated: false, asOf: new Date().toISOString() };
}
