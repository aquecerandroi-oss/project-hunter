"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useTransition } from "react";
import { DEFAULT_AUTO_REFRESH_INTERVAL_MS, shouldSkipAutoRefreshTick } from "@/lib/auto-refresh-interval";

export interface AutoRefreshProps {
  intervalMs?: number;
}

/**
 * Server Components render once per request; `export const revalidate` only
 * regenerates the cached response for the *next* request (ISR), it never
 * touches a tab that is already open. Left alone, a Server-Component page
 * fetched once reads as increasingly stale the longer the tab stays open --
 * every market badge eventually says "atrasado" even with perfectly healthy
 * ingestion, and a dead worker keeps its last-known green `alive` badge next
 * to an ever-growing age (T1.5 review F2).
 *
 * This calls `router.refresh()` on an interval to re-run the page's server
 * fetches in place, and pauses while the tab is hidden
 * (`document.visibilityState`) so a backgrounded tab never polls the API for
 * nothing. Renders nothing -- mount it anywhere in a page's server-rendered
 * tree.
 *
 * T3.51 (Everton on the VPS: "eu clico e não resolve nada"): a tab/pager
 * click can still be settling when the next tick fires; `router.refresh()`
 * re-fetching mid/right-after-navigation risks a stale snapshot winning the
 * race and the page reading as if the click "did nothing".
 * `shouldSkipAutoRefreshTick` (pure, unit-tested on its own) adds two guards
 * on top of the pre-existing visibility check: never stack a second
 * `router.refresh()` on one still pending, and never fire within
 * `AUTO_REFRESH_NAVIGATION_GUARD_MS` of `window.location.href` having just
 * changed. Reads `window.location.href` directly rather than
 * `usePathname()`/`useSearchParams()` on purpose -- this component is
 * mounted bare in several Server-Component pages it doesn't own, and
 * `useSearchParams()` would force every one of them into a `<Suspense>`
 * boundary it doesn't otherwise need.
 */
export function AutoRefresh({ intervalMs = DEFAULT_AUTO_REFRESH_INTERVAL_MS }: AutoRefreshProps) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();

  // The interval callback below closes over the render it was created in;
  // these refs let the same long-lived interval read the *current*
  // pending/URL state on every tick instead of a stale snapshot from mount
  // time. Written only from effects/the interval callback, never during
  // render, so both stay refs a React Compiler-era lint can trust are never
  // read for rendering (react-hooks/refs, react-hooks/purity).
  const isPendingRef = useRef(false);
  const lastHrefRef = useRef<string | null>(null);
  const lastNavigationAtRef = useRef<number | null>(null);

  useEffect(() => {
    isPendingRef.current = isPending;
  }, [isPending]);

  useEffect(() => {
    const id = window.setInterval(() => {
      const currentHref = window.location.href;
      if (lastHrefRef.current !== null && currentHref !== lastHrefRef.current) {
        // The URL changed since the last tick (a `router.push` -- tab,
        // pager, filter -- or a back/forward navigation) landed sometime in
        // this interval; skip this tick and start the settle window fresh
        // instead of possibly re-fetching mid-navigation.
        lastNavigationAtRef.current = Date.now();
      }
      lastHrefRef.current = currentHref;

      // No navigation observed yet (the first tick after mount): the guard
      // must not fire -- initialising the anchor inside this same tick made
      // `msSinceNavigation` read ~0 and silently dropped the first refresh
      // of every page (T3.51 review, CRITICAL).
      const msSinceNavigation =
        lastNavigationAtRef.current === null ? Number.POSITIVE_INFINITY : Date.now() - lastNavigationAtRef.current;
      const skip = shouldSkipAutoRefreshTick({
        visible: document.visibilityState === "visible",
        refreshPending: isPendingRef.current,
        msSinceNavigation,
      });
      if (skip) return;
      startTransition(() => router.refresh());
    }, intervalMs);
    return () => window.clearInterval(id);
  }, [router, intervalMs]);

  return null;
}
