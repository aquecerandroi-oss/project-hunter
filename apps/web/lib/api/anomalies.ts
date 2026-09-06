import "server-only";

import { apiFetch } from "@/lib/server/api";

import type { AnomaliesParams, AnomalyPage } from "./anomalies-types";

function anomaliesQuery(params: AnomaliesParams): string {
  const search = new URLSearchParams();
  if (params.window_hours !== undefined) search.set("window_hours", String(params.window_hours));
  if (params.type !== undefined) search.set("type", params.type);
  if (params.status !== undefined) search.set("status", params.status);
  if (params.market_id !== undefined) search.set("market_id", params.market_id);
  if (params.min_severity !== undefined) search.set("min_severity", params.min_severity);
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  if (params.cursor !== undefined) search.set("cursor", params.cursor);
  const value = search.toString();
  return value ? `?${value}` : "";
}

/**
 * `GET /api/v1/anomalies` (`apps/api/hunter_api/routers/anomalies.py`, T2.6).
 * Windowed by `detected_at` (default/max 24h/720h) -- never "every anomaly
 * that is currently active", since an `active + unknown` anomaly can be
 * arbitrarily old (`evaluation_state` docstring, `schemas/anomalies.py:3`).
 * Callers that build an aggregate from this (the radar table's column, the
 * market-detail timeline) must say so in the UI (Astra's T2.7 review,
 * must-fix 2) rather than present it as a complete "active now" count.
 */
export async function listAnomalies(params: AnomaliesParams = {}): Promise<AnomalyPage> {
  return apiFetch<AnomalyPage>(`/api/v1/anomalies${anomaliesQuery(params)}`);
}
