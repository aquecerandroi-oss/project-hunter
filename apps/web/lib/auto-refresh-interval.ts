/**
 * Pure auto-refresh cadence helpers, shared by Server Components (Markets,
 * market detail, System pages) and the client `AutoRefresh` component.
 * Lives outside the "use client" module on purpose: a function exported from
 * a client module becomes a client reference and cannot be called during
 * server rendering.
 */

/**
 * Fallback for pages with no `stale_after_ms` of their own (System -- see
 * `autoRefreshIntervalMs` below for pages that do, e.g. Markets and market
 * detail, H9). 12s: fast enough that a badge reading "atrasado" still means
 * something, slow enough not to hammer the API for a page with no realtime
 * channel of its own.
 */
export const DEFAULT_AUTO_REFRESH_INTERVAL_MS = 12_000;

/** Never refresh faster than this, no matter how low `stale_after_ms` is configured -- protects a ~200-row market universe from being hammered by a misconfigured tiny threshold (H9). */
export const MIN_AUTO_REFRESH_INTERVAL_MS = 3_000;

/**
 * How far below `stale_after_ms` a refresh must land (H9). Refreshing AT or
 * AFTER the threshold guarantees at least one component reads "atrasado" on
 * every single cycle even under perfectly healthy ingestion --
 * `router.refresh()` only re-fetches, it does not itself reset any
 * component's age, so the fetch has to land comfortably before the age it is
 * trying to keep ahead of.
 */
export const AUTO_REFRESH_SAFETY_MARGIN_MS = 3_000;

/**
 * Derives a refresh cadence from the API's own `stale_after_ms`
 * (`MarketListPage`/`MarketDetailOut`, H2) instead of a cadence hardcoded
 * independently of it -- see `AUTO_REFRESH_SAFETY_MARGIN_MS`/
 * `MIN_AUTO_REFRESH_INTERVAL_MS` above for the relationship each bound
 * enforces.
 */
export function autoRefreshIntervalMs(staleAfterMs: number): number {
  return Math.max(MIN_AUTO_REFRESH_INTERVAL_MS, staleAfterMs - AUTO_REFRESH_SAFETY_MARGIN_MS);
}

