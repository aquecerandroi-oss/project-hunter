import "server-only";

import { apiFetch } from "@/lib/server/api";

import { latencyOutSchema, type LatencyOut } from "./latency-types";

/**
 * `GET /api/v1/system/latency` (brief T3.79, frozen in
 * `.claude/state/notes-T3.79.md`) -- VIEWER+, i.e. any authenticated member,
 * not a tenant route: `CurrentPrincipal` alone is enough, same as
 * `/system/workers` and `/system/market-status` (`lib/api/system.ts`).
 * `.parse()`s the response before this app trusts it -- this router has no
 * generated OpenAPI type yet (same reasoning as `lab-daily-goal.ts`).
 */
export async function getLatency(): Promise<LatencyOut> {
  const raw = await apiFetch<unknown>("/api/v1/system/latency");
  return latencyOutSchema.parse(raw);
}
