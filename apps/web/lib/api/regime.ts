import "server-only";

import { apiFetch } from "@/lib/server/api";

import type { RegimeCurrentOut, RegimeHistoryPage, RegimeHistoryParams } from "./regime-types";

function historyQuery(params: RegimeHistoryParams): string {
  const search = new URLSearchParams();
  if (params.scope !== undefined) search.set("scope", params.scope);
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  if (params.cursor !== undefined) search.set("cursor", params.cursor);
  const value = search.toString();
  return value ? `?${value}` : "";
}

/**
 * `GET /api/v1/regime` (`apps/api/hunter_api/routers/regime.py`, T2.6) --
 * one row per `RegimeScope` (`global`/`btc`), each with its own `is_stale`.
 * There is no "regime per individual market" in this schema
 * (`.claude/state/notes-T2.6.md`'s recorded interpretation) -- never invent
 * one when rendering this.
 */
export async function getCurrentRegime(): Promise<RegimeCurrentOut> {
  return apiFetch<RegimeCurrentOut>("/api/v1/regime");
}

/** `GET /api/v1/regime/history` -- cursor-paginated, newest first. */
export async function getRegimeHistory(params: RegimeHistoryParams = {}): Promise<RegimeHistoryPage> {
  return apiFetch<RegimeHistoryPage>(`/api/v1/regime/history${historyQuery(params)}`);
}
