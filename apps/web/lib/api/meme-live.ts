import "server-only";

import { apiFetch } from "@/lib/server/api";

import { type MemeLive, memeLiveBase } from "./meme-live-types";

/**
 * `GET /api/v1/orgs/{org_id}/meme/live` (T4.14/T4.17, `routers/meme_live.py`)
 * -- the real executor's heartbeat, ledger and label REAL. `"server-only"`
 * like `lib/api/meme-desk.ts`; the write (`sell-now`) lives in
 * `meme-live-actions.ts` ("use server").
 */
export async function getMemeLive(orgId: string): Promise<MemeLive> {
  return apiFetch<MemeLive>(memeLiveBase(orgId));
}
