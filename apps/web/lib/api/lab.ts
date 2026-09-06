import "server-only";

import { apiFetch } from "@/lib/server/api";

import type { LabSignalsPage, LabSummaryOut, LabVersionsOut } from "./lab-types";

/** `GET /api/v1/lab/shadow/versions` -- the small, frozen catalogue (contract-S3-lab.md). */
export async function listLabVersions(): Promise<LabVersionsOut> {
  return apiFetch<LabVersionsOut>("/api/v1/lab/shadow/versions");
}

export interface LabSummaryParams {
  window?: "7d" | "30d" | "all";
  cohort?: string;
  as_of?: string;
}

function summaryQuery(params: LabSummaryParams): string {
  const search = new URLSearchParams();
  if (params.window !== undefined) search.set("window", params.window);
  if (params.cohort !== undefined) search.set("cohort", params.cohort);
  if (params.as_of !== undefined) search.set("as_of", params.as_of);
  const value = search.toString();
  return value ? `?${value}` : "";
}

/** `GET /api/v1/lab/shadow/summary` -- one object per activated `strategy_version` (contract-S3-lab.md). */
export async function getLabSummary(params: LabSummaryParams = {}): Promise<LabSummaryOut> {
  return apiFetch<LabSummaryOut>(`/api/v1/lab/shadow/summary${summaryQuery(params)}`);
}

export interface LabSignalsParams {
  strategy_version_id?: string;
  market?: string;
  tracking_state?: string;
  result?: string;
  cohort?: string;
  cursor?: string;
  limit?: number;
  /** `["envelope"]` includes `supporting_features` -- omitted by default (contract-S3-lab.md). */
  include?: string[];
}

function signalsQuery(params: LabSignalsParams): string {
  const search = new URLSearchParams();
  if (params.strategy_version_id !== undefined) search.set("strategy_version_id", params.strategy_version_id);
  if (params.market !== undefined) search.set("market", params.market);
  if (params.tracking_state !== undefined) search.set("tracking_state", params.tracking_state);
  if (params.result !== undefined) search.set("result", params.result);
  if (params.cohort !== undefined) search.set("cohort", params.cohort);
  if (params.cursor !== undefined) search.set("cursor", params.cursor);
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  for (const item of params.include ?? []) search.append("include", item);
  const value = search.toString();
  return value ? `?${value}` : "";
}

/**
 * `GET /api/v1/lab/shadow/signals` -- cursor-paginated, stable by
 * `(decision_at, id)`. This endpoint does NOT accept `window`/`as_of`
 * (contract-S3-lab.md, confirmed by `routers/lab.py::list_signals`) -- it
 * always returns the full available period for whatever filters are given;
 * only `/summary` is windowed. Callers must say so in the UI rather than
 * imply the summary's window also scopes this list (Astra, S3b hierarchy
 * review, must-fix).
 */
export async function getLabSignals(params: LabSignalsParams = {}): Promise<LabSignalsPage> {
  return apiFetch<LabSignalsPage>(`/api/v1/lab/shadow/signals${signalsQuery(params)}`);
}
