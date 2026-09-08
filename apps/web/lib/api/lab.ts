import "server-only";

import { apiFetch } from "@/lib/server/api";

import type { CurveOut, LabSignalsPage, LabSummaryOut, LabVersionsOut, ScoreboardOut } from "./lab-types";

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

export interface LabScoreboardParams {
  as_of?: string;
}

function scoreboardQuery(params: LabScoreboardParams): string {
  const search = new URLSearchParams();
  if (params.as_of !== undefined) search.set("as_of", params.as_of);
  const value = search.toString();
  return value ? `?${value}` : "";
}

/**
 * `GET /api/v1/lab/shadow/scoreboard` (brief T3.18) -- one row per
 * `strategy_version` that has ever emitted a signal, with the mechanical
 * verdict. Global/no-RLS like the rest of the Shadow Lab (no tenant scope in
 * the path -- `notes-T3.18.md`'s recorded architecture decision).
 */
export async function getLabScoreboard(params: LabScoreboardParams = {}): Promise<ScoreboardOut> {
  return apiFetch<ScoreboardOut>(`/api/v1/lab/shadow/scoreboard${scoreboardQuery(params)}`);
}

export interface LabCurveParams {
  version_id: string;
  as_of?: string;
  /**
   * T3.18b (brief T3.24b addendum A4): `"prospective"` (default), the
   * `"replay"` wildcard (every `replay:<uuid>` cohort of the version at
   * once) or one exact cohort string (`replay:<uuid>` /
   * `replication:<parent>:<k>`) -- anything else is a 422 from the API.
   */
  cohort?: string;
}

function curveQuery(params: LabCurveParams): string {
  const search = new URLSearchParams();
  search.set("version_id", params.version_id);
  if (params.as_of !== undefined) search.set("as_of", params.as_of);
  if (params.cohort !== undefined) search.set("cohort", params.cohort);
  return `?${search.toString()}`;
}

/** `GET /api/v1/lab/shadow/curve?version_id=` (brief T3.18, `cohort=` added by T3.18b) -- one call per version, capped at 2 000 points (`truncated`). */
export async function getLabCurve(params: LabCurveParams): Promise<CurveOut> {
  return apiFetch<CurveOut>(`/api/v1/lab/shadow/curve${curveQuery(params)}`);
}
