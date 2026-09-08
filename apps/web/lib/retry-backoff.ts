/**
 * Shared exponential-backoff schedule for a layout-level retry after a
 * recoverable API failure (brief T3.28b: `[orgSlug]/layout.tsx`'s `/me`
 * fetch hitting 429/5xx/network). Three attempts, doubling each time, then
 * the caller stops auto-retrying and leaves a manual button as the only way
 * forward -- a runaway retry loop must never out-live the caller's own
 * patience, and three doublings from 2s (2s, 4s, 8s = 14s total) comfortably
 * clears a request that only needed the API's own rate-limit window
 * (`WINDOW_SECONDS = 60` in `apps/api/hunter_api/middleware/rate_limit.py`)
 * to roll forward without hammering it while it does.
 */
export const MAX_AUTO_RETRIES = 3;

const BASE_DELAY_MS = 2000;

/** `attempt` is 1-based (the 1st retry, 2nd, 3rd); each one doubles the previous delay. */
export function backoffDelayMs(attempt: number): number {
  return BASE_DELAY_MS * 2 ** (attempt - 1);
}
