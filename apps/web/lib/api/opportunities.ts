import "server-only";

import { apiFetch } from "@/lib/server/api";

import type {
  OpportunitiesParams,
  OpportunityDetailOut,
  OpportunityDetailParams,
  OpportunityListPage,
} from "./opportunities-types";

function listQuery(params: OpportunitiesParams): string {
  const search = new URLSearchParams();
  if (params.org_id !== undefined) search.set("org_id", params.org_id);
  if (params.score_min !== undefined) search.set("score_min", params.score_min);
  for (const value of params.status ?? []) search.append("status", value);
  for (const value of params.stage ?? []) search.append("stage", value);
  if (params.exchange !== undefined) search.set("exchange", params.exchange);
  if (params.q !== undefined) search.set("q", params.q);
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  if (params.cursor !== undefined) search.set("cursor", params.cursor);
  const value = search.toString();
  return value ? `?${value}` : "";
}

/** `GET /api/v1/opportunities` (T2.6) -- no `decomposition` on any row (MF-2); see `getOpportunity` for the detail. */
export async function listOpportunities(params: OpportunitiesParams = {}): Promise<OpportunityListPage> {
  return apiFetch<OpportunityListPage>(`/api/v1/opportunities${listQuery(params)}`);
}

function detailQuery(params: OpportunityDetailParams): string {
  const search = new URLSearchParams();
  if (params.org_id !== undefined) search.set("org_id", params.org_id);
  if (params.include_envelope !== undefined) search.set("include_envelope", String(params.include_envelope));
  if (params.history_limit !== undefined) search.set("history_limit", String(params.history_limit));
  const value = search.toString();
  return value ? `?${value}` : "";
}

/**
 * `GET /api/v1/opportunities/{id}` (T2.6) -- the full "why are we looking
 * at this?" contract: decomposition, pt-BR explanation, active anomalies,
 * feature snapshot, score history. `include_envelope=true` caps
 * `history_limit` at 50 (422 above that, `MAX_ENVELOPE_HISTORY_LIMIT`).
 */
export async function getOpportunity(id: string, params: OpportunityDetailParams = {}): Promise<OpportunityDetailOut> {
  return apiFetch<OpportunityDetailOut>(`/api/v1/opportunities/${encodeURIComponent(id)}${detailQuery(params)}`);
}
