import "server-only";

import { isApiError } from "@/lib/api-error";
import { logger } from "@/lib/logger";
import { apiFetch } from "@/lib/server/api";

import { memeDeskBase } from "./meme-desk-types";
import type { MemeLabOut } from "./meme-lab-types";

export interface GetMemeLabParams {
  days?: number;
}

/** `GET /api/v1/orgs/{org_id}/meme/lab` (T4.6) -- the paper Lab's scoreboard per rule set, `days` bounded `[1, 90]` server-side. */
export async function getMemeLab(orgId: string, params: GetMemeLabParams = {}): Promise<MemeLabOut> {
  const query = params.days !== undefined ? `?days=${params.days}` : "";
  return apiFetch<MemeLabOut>(`${memeDeskBase(orgId)}/lab${query}`);
}

export type MemeArmsLoad = { ok: true; data: MemeLabOut } | { ok: false; reason: string };

/**
 * `components/meme-lab/meme-arms-board.tsx`'s own data, shared by
 * `/meme/testes` and `/meme/mesa?tab=testes` (the `lib/api/meme.ts::loadMemeSources`
 * convention: the try/catch lives once here, not duplicated per page). A
 * failure never blocks the day-scoped test record next to it -- its own
 * `SectionUnavailable`.
 */
export async function loadMemeArms(orgId: string, params: GetMemeLabParams = {}): Promise<MemeArmsLoad> {
  try {
    return { ok: true, data: await getMemeLab(orgId, params) };
  } catch (error) {
    const reason = isApiError(error) ? (error.detail ?? error.message) : error instanceof Error ? error.message : "erro desconhecido";
    logger.error("meme_arms_load_failed", { error: reason });
    return { ok: false, reason };
  }
}
