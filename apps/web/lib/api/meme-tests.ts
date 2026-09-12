import "server-only";

import { isApiError } from "@/lib/api-error";
import { apiFetch, apiFetchResponse } from "@/lib/server/api";
import { logger } from "@/lib/logger";

import { memeDeskBase } from "./meme-desk-types";
import type { MemeTestDetail, MemeTests } from "./meme-tests-types";

/**
 * `GET /api/v1/orgs/{org_id}/meme/tests` (T4.13, `routers/meme_tests.py`) --
 * every test of a Brasília day, plus the CSV export and one bet's record.
 * `"server-only"` like `lib/api/meme-desk.ts`; there is no write here.
 */
export interface GetMemeTestsParams {
  /** `YYYY-MM-DD` (Brasília); the API defaults to today when absent. */
  day?: string | undefined;
  ruleSet?: string | undefined;
  limit?: number | undefined;
  cursor?: string | undefined;
}

/** The query string the API understands (`day`, `rule_set`, `limit`, `cursor`) -- exported for `tests/meme-tests.test.ts`. */
export function memeTestsQuery(params: GetMemeTestsParams): string {
  const search = new URLSearchParams();
  if (params.day !== undefined) search.set("day", params.day);
  if (params.ruleSet !== undefined) search.set("rule_set", params.ruleSet);
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  if (params.cursor !== undefined) search.set("cursor", params.cursor);
  const value = search.toString();
  return value ? `?${value}` : "";
}

export async function getMemeTests(orgId: string, params: GetMemeTestsParams = {}): Promise<MemeTests> {
  return apiFetch<MemeTests>(`${memeDeskBase(orgId)}/tests${memeTestsQuery(params)}`);
}

export async function getMemeTestDetail(orgId: string, betId: string): Promise<MemeTestDetail> {
  return apiFetch<MemeTestDetail>(`${memeDeskBase(orgId)}/tests/${encodeURIComponent(betId)}`);
}

/** The CSV as the API rendered it (UTF-8 with BOM, `;`), for the route handler that hands it to the browser. */
export async function fetchMemeTestsCsv(orgId: string, params: Pick<GetMemeTestsParams, "day" | "ruleSet">): Promise<Response> {
  return apiFetchResponse(`${memeDeskBase(orgId)}/tests.csv${memeTestsQuery(params)}`, "text/csv");
}

export type MemeTestsLoad = { ok: true; data: MemeTests } | { ok: false; reason: string };

/** `getMemeTests` that never throws -- the "Testes" tab is one section of a page whose other sections must still render. */
export async function loadMemeTests(orgId: string, params: GetMemeTestsParams = {}): Promise<MemeTestsLoad> {
  try {
    return { ok: true, data: await getMemeTests(orgId, params) };
  } catch (error) {
    const reason = isApiError(error) ? (error.detail ?? error.message) : error instanceof Error ? error.message : "erro desconhecido";
    logger.error("meme_tests_load_failed", { error: reason });
    return { ok: false, reason };
  }
}
