"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { DEFAULT_AUTO_REFRESH_INTERVAL_MS } from "@/lib/auto-refresh-interval";

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
 */
export function AutoRefresh({ intervalMs = DEFAULT_AUTO_REFRESH_INTERVAL_MS }: AutoRefreshProps) {
  const router = useRouter();

  useEffect(() => {
    const id = window.setInterval(() => {
      if (document.visibilityState !== "visible") return;
      router.refresh();
    }, intervalMs);
    return () => window.clearInterval(id);
  }, [router, intervalMs]);

  return null;
}
