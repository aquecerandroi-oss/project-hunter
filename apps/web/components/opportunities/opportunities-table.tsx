"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { OpportunitiesEmpty } from "@/components/opportunities/opportunities-empty";
import { OpportunityRow } from "@/components/opportunities/opportunity-row";
import { OPPORTUNITIES_TABLE_HEADERS, OpportunitiesTableHead } from "@/components/opportunities/opportunities-table-head";
import { Button } from "@/components/ui/button";
import { useArrowKeyRowSelection } from "@/hooks/useArrowKeyRowSelection";
import { useRowHeight } from "@/hooks/useDensity";
import { useVirtualizedRows } from "@/hooks/useVirtualizedRows";
import { loadOpportunitiesAction } from "@/lib/api/opportunities-actions";
import type { OpportunitiesParams, OpportunitySummaryOut } from "@/lib/api/opportunities-types";
import { logger } from "@/lib/logger";

export interface OpportunitiesTableProps {
  orgSlug: string;
  initialItems: OpportunitySummaryOut[];
  initialCursor: string | null;
  hasFilters: boolean;
  baseParams: OpportunitiesParams;
}

const OVERSCAN = 8;
const VIEWPORT_HEIGHT = 480;
const HEADER_HEIGHT = 32;

function rowId(row: OpportunitySummaryOut): string {
  return `opportunity-row-${row.id}`;
}

/**
 * `/opportunities`'s compact index (Astra's T2.7 review: "índice compacto de
 * episódios", the full discovery surface with rich filters + realtime lives
 * at `/radar`). No `rt:radar` subscription here on purpose -- one live
 * table is enough; this one relies on `AutoRefresh` on the page for periodic
 * revalidation, same as `/lab`.
 */
export function OpportunitiesTable({ orgSlug, initialItems, initialCursor, hasFilters, baseParams }: OpportunitiesTableProps) {
  const router = useRouter();
  const rowHeight = useRowHeight();
  const [items, setItems] = useState(initialItems);
  const [cursor, setCursor] = useState(initialCursor);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const requestIdRef = useRef(0);

  useEffect(() => {
    // The Server Component page passes a genuinely new `initialItems`/
    // `initialCursor` on every filter/sort navigation (`opportunities/page.tsx`
    // re-fetches on its own `searchParams`) -- this used to only seed the
    // initial `useState`, so changing a filter kept showing the previous
    // filter's rows forever (Astra's T2.7 diff review, must-fix 2). Bumping
    // the request id also discards any `loadMore` still in flight for the
    // filters being replaced.
    requestIdRef.current += 1;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- resyncing from a genuinely new server-provided page (filters/sort changed), an external input to this component
    setItems(initialItems);
    setCursor(initialCursor);
  }, [initialItems, initialCursor]);

  const { startIndex, endIndex, visibleRows, topPad, bottomPad } = useVirtualizedRows({
    rows: items,
    rowHeight,
    scrollTop,
    viewportHeight: VIEWPORT_HEIGHT,
    overscan: OVERSCAN,
  });

  const { selectedIndex, handleKeyDown } = useArrowKeyRowSelection({
    rowCount: items.length,
    rowHeight,
    viewportHeight: VIEWPORT_HEIGHT,
    stickyHeaderHeight: HEADER_HEIGHT,
    getScrollContainer: () => containerRef.current,
    onOpen: (index) => {
      const row = items[index];
      if (row) router.push(`/${orgSlug}/opportunities/${row.id}`);
    },
  });

  const selectedRow = selectedIndex >= startIndex && selectedIndex < endIndex ? items[selectedIndex] : undefined;

  async function loadMore(): Promise<void> {
    if (!cursor || loadingMore) return;
    const myRequestId = ++requestIdRef.current;
    setLoadingMore(true);
    setLoadError(null);
    try {
      const outcome = await loadOpportunitiesAction({ ...baseParams, cursor });
      // The filters could have changed (a new `requestIdRef` bump from the
      // resync effect above) while this request was in flight -- applying a
      // stale page here would mix rows from two different filter sets.
      if (requestIdRef.current !== myRequestId) return;
      if (!outcome.ok) {
        setLoadError(outcome.reason ?? "erro desconhecido");
        return;
      }
      setItems((prev) => [...prev, ...outcome.page.items]);
      setCursor(outcome.page.next_cursor ?? null);
    } catch (error) {
      logger.error("opportunities_load_more_failed", { error: String(error) });
      if (requestIdRef.current === myRequestId) setLoadError("falha ao carregar mais oportunidades");
    } finally {
      if (requestIdRef.current === myRequestId) setLoadingMore(false);
    }
  }

  if (items.length === 0) return <OpportunitiesEmpty orgSlug={orgSlug} hasFilters={hasFilters} />;

  return (
    <div className="flex flex-col gap-3">
      <div className="overflow-x-auto rounded-md border border-border">
        <div
          ref={containerRef}
          onScroll={(e) => setScrollTop(e.currentTarget.scrollTop)}
          onKeyDown={handleKeyDown}
          tabIndex={0}
          role="grid"
          aria-label="Oportunidades"
          aria-activedescendant={selectedRow ? rowId(selectedRow) : undefined}
          aria-rowcount={items.length + 1}
          className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold"
          style={{ height: VIEWPORT_HEIGHT, overflowY: "auto" }}
        >
          <table role="presentation" className="w-full text-left text-[13px]">
            <OpportunitiesTableHead />
            <tbody>
              {topPad > 0 && (
                <tr aria-hidden="true" style={{ height: topPad }}>
                  <td colSpan={OPPORTUNITIES_TABLE_HEADERS.length} />
                </tr>
              )}
              {visibleRows.map((row, visibleOffset) => {
                const absoluteIndex = startIndex + visibleOffset;
                return (
                  <OpportunityRow
                    key={row.id}
                    id={rowId(row)}
                    orgSlug={orgSlug}
                    row={row}
                    rowHeight={rowHeight}
                    selected={absoluteIndex === selectedIndex}
                    ariaRowIndex={absoluteIndex + 2}
                    onOpen={() => router.push(`/${orgSlug}/opportunities/${row.id}`)}
                  />
                );
              })}
              {bottomPad > 0 && (
                <tr aria-hidden="true" style={{ height: bottomPad }}>
                  <td colSpan={OPPORTUNITIES_TABLE_HEADERS.length} />
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <Button type="button" variant="outline" size="sm" onClick={() => void loadMore()} disabled={!cursor || loadingMore}>
          {cursor ? (loadingMore ? "Carregando..." : "Carregar mais") : "Fim da lista"}
        </Button>
        {loadError && <span className="text-xs text-red">{loadError}</span>}
      </div>
    </div>
  );
}
