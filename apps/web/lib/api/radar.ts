import "server-only";

import { apiFetch } from "@/lib/server/api";

import type { RadarPage, RadarParams } from "./radar-types";

const SCALAR_KEYS = [
  "org_id",
  "score_min",
  "exchange",
  "anomaly_type",
  "regime",
  "volatility_min",
  "volatility_max",
  "q",
  "sort",
  "order",
  "limit",
  "cursor",
] as const satisfies readonly (keyof RadarParams)[];

const LIST_KEYS = ["status", "stage"] as const satisfies readonly (keyof RadarParams)[];

function radarQuery(params: RadarParams): string {
  const search = new URLSearchParams();
  for (const key of SCALAR_KEYS) {
    const value = params[key];
    if (value !== undefined) search.set(key, String(value));
  }
  for (const key of LIST_KEYS) {
    for (const value of params[key] ?? []) search.append(key, value);
  }
  const value = search.toString();
  return value ? `?${value}` : "";
}

/**
 * `GET /api/v1/radar` (`apps/api/hunter_api/routers/radar.py`, T2.6) -- one
 * row per scored `opportunities` episode (never a market row without one),
 * globally ranked. `org_id` only unlocks `in_position`/`risk_blocked` on
 * each row (`RadarPage.org_scoped`); every other field is identical for
 * every caller.
 */
export async function listRadar(params: RadarParams = {}): Promise<RadarPage> {
  return apiFetch<RadarPage>(`/api/v1/radar${radarQuery(params)}`);
}
