import "server-only";

import { isApiError } from "@/lib/api-error";
import { apiFetch } from "@/lib/server/api";
import { logger } from "@/lib/logger";

import { type MemeDesk, type MemeLoopState, memeDeskBase } from "./meme-desk-types";

/**
 * `GET /api/v1/orgs/{org_id}/meme/desk` (T4.7, `routers/meme_desk.py`) --
 * the operator desk: proposals awaiting approval first, then bets awaiting
 * fill, then open bets, then history, plus the per-rule-set paper balance.
 * `"server-only"` like `lib/api/meme.ts`; the writes live in
 * `meme-desk-actions.ts` ("use server").
 */
export interface GetMemeDeskParams {
  status?: string;
  limit?: number;
  cursor?: string;
}

function deskQuery(params: GetMemeDeskParams): string {
  const search = new URLSearchParams();
  if (params.status !== undefined) search.set("status", params.status);
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  if (params.cursor !== undefined) search.set("cursor", params.cursor);
  const value = search.toString();
  return value ? `?${value}` : "";
}

export async function getMemeDesk(orgId: string, params: GetMemeDeskParams = {}): Promise<MemeDesk> {
  return apiFetch<MemeDesk>(`${memeDeskBase(orgId)}/desk${deskQuery(params)}`);
}

function readLastTickAt(payload: unknown): string | null | undefined {
  if (payload === null || typeof payload !== "object") return undefined;
  const sources = (payload as { sources?: unknown }).sources;
  if (sources === null || typeof sources !== "object") return undefined;
  const value = (sources as { lab_last_tick_at?: unknown }).lab_last_tick_at;
  if (value === null) return null;
  return typeof value === "string" ? value : undefined;
}

/**
 * The loop's liveness off `GET /meme/lab` (T4.6, built in parallel). Three
 * honest outcomes besides a reading: the endpoint does not exist yet
 * (`endpoint_missing`), it failed (`read_failed`), or it answered with a
 * shape that does not carry `sources.lab_last_tick_at` (`shape_unknown`).
 * Never throws: the desk renders without the loop's state rather than
 * failing because a sibling endpoint is not there.
 */
export async function getMemeLoopState(orgId: string): Promise<MemeLoopState> {
  try {
    const payload = await apiFetch<unknown>(`${memeDeskBase(orgId)}/lab`);
    const lastTickAt = readLastTickAt(payload);
    if (lastTickAt === undefined) return { lastTickAt: null, reason: "shape_unknown" };
    return { lastTickAt, reason: null };
  } catch (error) {
    if (isApiError(error) && error.status === 404) return { lastTickAt: null, reason: "endpoint_missing" };
    const reason = isApiError(error) ? (error.detail ?? error.message) : String(error);
    logger.warn("meme_lab_loop_state_unavailable", { error: reason });
    return { lastTickAt: null, reason: "read_failed" };
  }
}
