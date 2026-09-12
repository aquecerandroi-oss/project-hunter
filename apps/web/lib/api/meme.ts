import "server-only";

import { isApiError } from "@/lib/api-error";
import { apiFetch } from "@/lib/server/api";
import { logger } from "@/lib/logger";

import type { MemeGapList, MemeOverview, MemeSources, MemeTokenDetail, MemeTokenList, MemeTokenSort, MemeTokenState } from "./meme-types";

/**
 * `GET /api/v1/orgs/{org_id}/meme/**` (T4.3, `routers/meme.py`) -- read-only
 * Meme Radar reads. Every function here is `"server-only"` (same boundary as
 * `lib/api/portfolio.ts`); there is no mutation in this file because the
 * Meme Radar is monitoring-only (`docs/plans/T4-MEME-RADAR.md` §0 -- no
 * order, no wallet, no `RiskDecision`).
 */
function memeBase(orgId: string): string {
  return `/api/v1/orgs/${orgId}/meme`;
}

/** Coins created 24h/7d, Mayhem activity, graduations -- real data, two possible sources (see `MemeOverviewOut`'s own docstring). */
export async function getMemeOverview(orgId: string): Promise<MemeOverview> {
  return apiFetch<MemeOverview>(`${memeBase(orgId)}/overview`);
}

export interface ListMemeTokensParams {
  state?: MemeTokenState;
  sort?: MemeTokenSort;
  limit?: number;
  cursor?: string;
}

function tokensQuery(params: ListMemeTokensParams): string {
  const search = new URLSearchParams();
  if (params.state !== undefined) search.set("state", params.state);
  if (params.sort !== undefined) search.set("sort", params.sort);
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  if (params.cursor !== undefined) search.set("cursor", params.cursor);
  const value = search.toString();
  return value ? `?${value}` : "";
}

/** The radar list -- the latest closed minute of `meme_features_1m`, joined to token identity. */
export async function listMemeTokens(orgId: string, params: ListMemeTokensParams = {}): Promise<MemeTokenList> {
  return apiFetch<MemeTokenList>(`${memeBase(orgId)}/tokens${tokensQuery(params)}`);
}

export interface GetMemeTokenParams {
  snapshot_limit?: number;
  feature_limit?: number;
}

function tokenDetailQuery(params: GetMemeTokenParams): string {
  const search = new URLSearchParams();
  if (params.snapshot_limit !== undefined) search.set("snapshot_limit", String(params.snapshot_limit));
  if (params.feature_limit !== undefined) search.set("feature_limit", String(params.feature_limit));
  const value = search.toString();
  return value ? `?${value}` : "";
}

/** One token: identity + latest curve reading, the curve snapshot series, and the per-minute feature series. */
export async function getMemeToken(orgId: string, mint: string, params: GetMemeTokenParams = {}): Promise<MemeTokenDetail> {
  return apiFetch<MemeTokenDetail>(`${memeBase(orgId)}/tokens/${encodeURIComponent(mint)}${tokenDetailQuery(params)}`);
}

export interface ListMemeGapsParams {
  limit?: number;
  cursor?: string;
}

function gapsQuery(params: ListMemeGapsParams): string {
  const search = new URLSearchParams();
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  if (params.cursor !== undefined) search.set("cursor", params.cursor);
  const value = search.toString();
  return value ? `?${value}` : "";
}

/** Ingestion gaps -- declared, never silenced (WS reconnects, REST rate limits). */
export async function listMemeGaps(orgId: string, params: ListMemeGapsParams = {}): Promise<MemeGapList> {
  return apiFetch<MemeGapList>(`${memeBase(orgId)}/gaps${gapsQuery(params)}`);
}

/** The radar's sources (T4.2c/T4.3b, `routers/meme_sources.py`): heartbeat per source, coverage of the last folded minute, declared discovery blindness. */
export async function getMemeSources(orgId: string): Promise<MemeSources> {
  return apiFetch<MemeSources>(`${memeBase(orgId)}/sources`);
}

export type MemeSourcesLoad = { ok: true; data: MemeSources } | { ok: false; reason: string };

/**
 * `getMemeSources` that never throws -- shared by `/meme` and `/meme/mesa`
 * (brief T4.3b): the panel is one section of a page whose other sections
 * must still render when this read fails, so the failure comes back named
 * and the page hands it to `SectionUnavailable`.
 */
export async function loadMemeSources(orgId: string): Promise<MemeSourcesLoad> {
  try {
    return { ok: true, data: await getMemeSources(orgId) };
  } catch (error) {
    const reason = isApiError(error) ? (error.detail ?? error.message) : error instanceof Error ? error.message : "erro desconhecido";
    logger.error("meme_sources_load_failed", { error: reason });
    return { ok: false, reason };
  }
}
