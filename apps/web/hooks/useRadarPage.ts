"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { loadRadarAnomaliesAggregateAction } from "@/lib/api/anomalies-actions";
import type { AnomaliesAggregate } from "@/lib/api/anomalies-types";
import { loadRadarAction } from "@/lib/api/radar-actions";
import type { RadarItemOut, RadarParams } from "@/lib/api/radar-types";
import { logger } from "@/lib/logger";

export interface UseRadarPageOptions {
  initialItems: RadarItemOut[];
  initialCursor: string | null;
  initialAsOf: string;
  /** The exact filters (minus `cursor`) behind the initial fetch -- reused for "load more" and every reconciliation. */
  baseParams: RadarParams;
  initialAnomalies: AnomaliesAggregate;
}

export interface UseRadarPageResult {
  items: RadarItemOut[];
  cursor: string | null;
  asOf: string;
  anomalies: AnomaliesAggregate;
  loadingMore: boolean;
  loadError: string | null;
  /** A failed reconciliation (background 5s tick or `rt:radar` message) -- distinct from `loadError` (an explicit "load more" click), and never wipes the rows already on screen. */
  reconcileError: string | null;
  reconcile: () => Promise<void>;
  loadMore: () => Promise<void>;
}

/**
 * `/radar`'s client-side page state: the currently loaded rows, cursor,
 * query timestamp and anomalies aggregate, plus the two ways they change --
 * "load more" (cursor, same filters) and reconciliation (a fresh read
 * covering the currently-loaded depth, replacing what is loaded).
 *
 * **Request identity (Astra's T2.7 diff review, must-fix 1).** `reconcile`
 * and `loadMore` can race: a background reconciliation can resolve while a
 * "load more" is in flight, or vice versa, and applying both blindly could
 * duplicate rows (a reconciled page-1 followed by an in-flight page-2 that
 * no longer lines up with it) or silently drop a filter change. Every
 * dispatch takes a ticket from the same `requestIdRef`; a result only gets
 * applied if its ticket is still the current one when it resolves. This is a
 * "last dispatched wins, everything else is dropped" policy, not a merge --
 * a dropped "load more" simply gets superseded by the next 5s
 * reconciliation, which is an acceptable, honest trade-off for a table with
 * no real-time producer yet (`.claude/state/notes-T2.7.md`).
 */
export function useRadarPage({ initialItems, initialCursor, initialAsOf, baseParams, initialAnomalies }: UseRadarPageOptions): UseRadarPageResult {
  const [items, setItems] = useState(initialItems);
  const [cursor, setCursor] = useState(initialCursor);
  const [asOf, setAsOf] = useState(initialAsOf);
  const [anomalies, setAnomalies] = useState(initialAnomalies);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reconcileError, setReconcileError] = useState<string | null>(null);
  const requestIdRef = useRef(0);
  // A ref mirror of `items`/`baseParams`, read (not depended on) inside
  // `reconcile` so its identity stays stable across every row update --
  // otherwise the interval effect in `radar-table.tsx` would restart its 5s
  // countdown on every render. Same pattern as `useMarketChannels.ts`'s
  // `onMessageRef`.
  const stateRef = useRef({ items, baseParams });
  useEffect(() => {
    stateRef.current = { items, baseParams };
  });

  useEffect(() => {
    // A genuinely new server-provided page (filters/sort navigated to a new
    // URL) -- bump the request id so any in-flight reconcile/loadMore for
    // the PREVIOUS filters can never overwrite it once it resolves.
    requestIdRef.current += 1;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- resyncing from a genuinely new server-provided initial page (filters/sort changed), an external input to this hook
    setItems(initialItems);
    setCursor(initialCursor);
    setAsOf(initialAsOf);
    setAnomalies(initialAnomalies);
    setReconcileError(null);
  }, [initialItems, initialCursor, initialAsOf, initialAnomalies]);

  const reconcile = useCallback(async () => {
    const myRequestId = ++requestIdRef.current;
    const { items: currentItems, baseParams: currentParams } = stateRef.current;
    // Re-covers the depth already loaded (so paging further than page 1
    // survives a reconciliation) rather than always truncating back to a
    // single page -- the loaded rows are still a snapshot of a live-ranked
    // list, never claimed complete (the "carregar mais" footnote already
    // says so).
    const depth = Math.min(Math.max(currentItems.length, currentParams.limit ?? 200), 200);
    try {
      const [radarOutcome, anomaliesResult] = await Promise.all([
        loadRadarAction({ ...currentParams, limit: depth }),
        loadRadarAnomaliesAggregateAction(),
      ]);
      if (requestIdRef.current !== myRequestId) return; // superseded by a newer dispatch
      setAnomalies(anomaliesResult);
      if (radarOutcome.ok) {
        setItems(radarOutcome.page.items);
        setCursor(radarOutcome.page.next_cursor ?? null);
        setAsOf(radarOutcome.page.as_of);
        setReconcileError(null);
      } else {
        // MUST-FIX 4: a failed reconciliation used to leave `loadError`/
        // `reconcileError` untouched, so a 503 after a healthy load read as
        // "still healthy, just not updating" instead of a visible failure.
        setReconcileError(radarOutcome.reason ?? "erro desconhecido");
      }
    } catch (error) {
      if (requestIdRef.current !== myRequestId) return;
      logger.error("radar_reconcile_failed", { error: String(error) });
      setReconcileError("falha ao atualizar o radar");
    }
  }, []);

  const loadMore = useCallback(async () => {
    const { items: currentItems, baseParams: currentParams } = stateRef.current;
    if (!cursor || loadingMore) return;
    const myRequestId = ++requestIdRef.current;
    setLoadingMore(true);
    setLoadError(null);
    try {
      const outcome = await loadRadarAction({ ...currentParams, cursor });
      if (requestIdRef.current !== myRequestId) return; // filters/reconciliation superseded this request
      if (!outcome.ok) {
        setLoadError(outcome.reason ?? "erro desconhecido");
        return;
      }
      setItems([...currentItems, ...outcome.page.items]);
      setCursor(outcome.page.next_cursor ?? null);
    } catch (error) {
      if (requestIdRef.current !== myRequestId) return;
      logger.error("radar_load_more_failed", { error: String(error) });
      setLoadError("falha ao carregar mais oportunidades");
    } finally {
      if (requestIdRef.current === myRequestId) setLoadingMore(false);
    }
  }, [cursor, loadingMore]);

  return { items, cursor, asOf, anomalies, loadingMore, loadError, reconcileError, reconcile, loadMore };
}
