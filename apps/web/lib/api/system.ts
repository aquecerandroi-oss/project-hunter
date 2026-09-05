import "server-only";

import { logger } from "@/lib/logger";
import { apiFetch } from "@/lib/server/api";

import type { MarketStatusResponse, ReadyStatus, SystemInfo, WorkerHeartbeat } from "./types";

/** `GET /api/v1/system/info` (apps/api/hunter_api/health.py) -- public, unauthenticated. */
export async function systemInfo(): Promise<SystemInfo> {
  return apiFetch<SystemInfo>("/api/v1/system/info");
}

/** `GET /api/v1/system/workers` -- a bare array (`schemas/system.py`'s `list[WorkerHeartbeatOut]`); `market` role rows also carry `ws_state`/`markets_monitored`/etc. */
export async function getWorkers(): Promise<WorkerHeartbeat[]> {
  return apiFetch<WorkerHeartbeat[]>("/api/v1/system/workers");
}

/** `GET /api/v1/system/market-status` (T1.4) -- monitored count, WS state, last-tick age and open gaps per exchange. */
export async function getMarketStatus(): Promise<MarketStatusResponse> {
  return apiFetch<MarketStatusResponse>("/api/v1/system/market-status");
}

/**
 * `GET /ready` -- deliberately NOT built on `apiFetch`. `/ready` answers 200
 * only when Postgres and Redis both check out and 503 otherwise, but in
 * both cases the *body* (`{database, redis, database_detail?, redis_detail?}`)
 * is what the System page needs to render -- `apiFetch` treats any non-2xx
 * as a thrown `ApiError` and keeps only `type`/`title`/`status`/`detail`
 * from the response body, which would throw away exactly the per-dependency
 * detail a degraded reading exists to show (health.py's module docstring:
 * "honest 503 handling"). A plain, unauthenticated `fetch` mirrors what an
 * infra probe does against this same endpoint.
 */
export async function ready(): Promise<ReadyStatus> {
  // H7: the `API_URL` check used to sit BEFORE this `try`, so a missing
  // config threw straight out of `ready()` -- past the System page's own
  // `Promise.all` isolation (loadWorkers()/loadSystemInfo() render their own
  // honest per-section message; nothing does if the whole page's render
  // rejects first). Every exit from this function must be a normal return, so
  // the config check moves inside the same `try` as the fetch itself.
  try {
    const baseUrl = process.env.API_URL;
    if (!baseUrl) throw new Error("API_URL is not configured");

    const response = await fetch(`${baseUrl}/ready`, {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    const body = (await response.json()) as ReadyStatus;
    return body;
  } catch (error) {
    logger.error("ready_check_failed", { error: error instanceof Error ? error.message : String(error) });
    return { database: false, redis: false, database_detail: "unreachable", redis_detail: "unreachable" };
  }
}
