import "server-only";

import { logger } from "@/lib/logger";
import { apiFetch } from "@/lib/server/api";

import { READY_CHECK_NOT_CONFIGURED, wasReadyCheckAttempted } from "./ready-status";
import type { MarketStatusResponse, ReadyStatus, SystemInfo, WorkerHeartbeat } from "./types";

// Re-exported so every existing server-side caller (this file's own
// `ready()` below, `app/(app)/[orgSlug]/layout.tsx`, `dashboard/page.tsx`,
// `tests/api/system.test.ts`) keeps importing from `@/lib/api/system`
// unchanged -- see `./ready-status`'s docstring for why the definitions
// themselves had to move (H3, client-safe import for `readiness-panel.tsx`).
export { READY_CHECK_NOT_CONFIGURED, wasReadyCheckAttempted };

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
  // H7: a missing config used to throw straight out of `ready()` -- past the
  // System page's own `Promise.all` isolation. Every exit from this function
  // is a normal return; a missing `API_URL` returns its own sentinel detail
  // (`READY_CHECK_NOT_CONFIGURED`) instead of reaching the `try` at all --
  // there is nothing to attempt, so it is not the same case as the `catch`
  // below (a real, attempted check that failed).
  const baseUrl = process.env.API_URL;
  if (!baseUrl) {
    logger.error("ready_check_not_configured", {});
    return {
      database: false,
      redis: false,
      database_detail: READY_CHECK_NOT_CONFIGURED,
      redis_detail: READY_CHECK_NOT_CONFIGURED,
    };
  }

  try {
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
