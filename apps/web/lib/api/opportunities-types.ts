/**
 * Aliases onto the T2.6 opportunities contract
 * (`apps/api/hunter_api/routers/opportunities.py`, `schemas/opportunities.py`).
 * `decomposition`/`explanation`/`feature_snapshot`/`envelope` are typed as
 * `Record<string, unknown>` here, exactly as the API declares them
 * (`dict[str, Any]` -- schema module docstring: their shape is owned by
 * `hunter_indicators.opportunity`/the scanner-worker, not this contract).
 * `components/opportunities/decomposition-parse.ts` is the defensive
 * adapter that reads the real, current shape
 * (`packages/indicators/hunter_indicators/opportunity/{model,explanation,envelope}.py`)
 * with a raw-JSON fallback, per Astra's T2.7 review.
 */
import type { components } from "@hunter/shared-types/api";

export type OpportunitySummaryOut = components["schemas"]["OpportunitySummaryOut"];
export type OpportunityDetailOut = components["schemas"]["OpportunityDetailOut"];
export type OpportunityAnomalyOut = components["schemas"]["OpportunityAnomalyOut"];
export type OpportunityHistoryPointOut = components["schemas"]["OpportunityHistoryPointOut"];
/** `GET /api/v1/opportunities`'s cursor page shape (`CursorPage[OpportunitySummaryOut]`). */
export type OpportunityListPage = components["schemas"]["CursorPage_OpportunitySummaryOut_"];

export interface OpportunitiesParams {
  org_id?: string;
  score_min?: string;
  status?: string[];
  stage?: string[];
  exchange?: string;
  q?: string;
  limit?: number;
  cursor?: string;
}

export interface OpportunityDetailParams {
  org_id?: string;
  include_envelope?: boolean;
  history_limit?: number;
}

/** `MAX_ENVELOPE_HISTORY_LIMIT` (`schemas/opportunities.py`) -- the 422 ceiling when `include_envelope=true`. */
export const MAX_ENVELOPE_HISTORY_LIMIT = 50;
/** `MAX_HISTORY_LIMIT` (`schemas/opportunities.py`) -- the ceiling without the envelope. */
export const MAX_HISTORY_LIMIT = 500;
/** `DEFAULT_HISTORY_LIMIT` (`repositories/opportunities.py`). */
export const DEFAULT_HISTORY_LIMIT = 100;
