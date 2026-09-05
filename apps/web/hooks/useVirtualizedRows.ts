"use client";

import { useMemo } from "react";

export interface UseVirtualizedRowsOptions<T> {
  rows: T[];
  rowHeight: number;
  scrollTop: number;
  viewportHeight: number;
  /** Extra rows rendered above/below the visible window, so a fast scroll doesn't flash empty rows before the next render catches up. */
  overscan?: number;
}

export interface UseVirtualizedRowsResult<T> {
  startIndex: number;
  endIndex: number;
  visibleRows: T[];
  /** Height (px) of the leading `<tr>` spacer that stands in for every row above `startIndex`. */
  topPad: number;
  /** Height (px) of the trailing `<tr>` spacer that stands in for every row below `endIndex`. */
  bottomPad: number;
}

/**
 * Manual windowing math for `components/markets/markets-table.tsx` (M9,
 * T1.5b fix pass): extracted out to keep `MarketsTable` under the lint
 * config's per-function statement budget, and this arithmetic is
 * independently unit-testable (it is also the natural home for H1's
 * SSR-safe row height, since `hooks/useDensity.ts`'s `useRowHeight` is what
 * callers pass in as `rowHeight`). No extra dependency was authorized for
 * this task -- this is enough to satisfy CLAUDE.md's "tables virtualize at
 * >= 200 rows" for the ~200-row monitored universe.
 */
export function useVirtualizedRows<T>({
  rows,
  rowHeight,
  scrollTop,
  viewportHeight,
  overscan = 0,
}: UseVirtualizedRowsOptions<T>): UseVirtualizedRowsResult<T> {
  return useMemo(() => {
    // Clamped to `rows.length`: filtering to a shorter list must not leave
    // `startIndex` pointing past its end from a scroll position set against
    // the *previous*, longer list -- that would slice out an empty window
    // and hide real matches (Astra's T1.5 review).
    const maxStartIndex = Math.max(0, rows.length - 1);
    const startIndex = Math.min(maxStartIndex, Math.max(0, Math.floor(scrollTop / rowHeight) - overscan));
    const visibleCount = Math.ceil(viewportHeight / rowHeight) + overscan * 2;
    const endIndex = Math.min(rows.length, startIndex + visibleCount);
    const visibleRows = rows.slice(startIndex, endIndex);
    const topPad = startIndex * rowHeight;
    const bottomPad = (rows.length - endIndex) * rowHeight;
    return { startIndex, endIndex, visibleRows, topPad, bottomPad };
  }, [rows, rowHeight, scrollTop, viewportHeight, overscan]);
}
