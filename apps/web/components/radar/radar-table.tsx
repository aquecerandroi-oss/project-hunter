"use client";

import { useAuth } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { RadarEmpty } from "@/components/radar/radar-empty";
import { RadarRow } from "@/components/radar/radar-row";
import { RADAR_TABLE_HEADERS, RadarTableHead } from "@/components/radar/radar-table-head";
import { Button } from "@/components/ui/button";
import { useArrowKeyRowSelection } from "@/hooks/useArrowKeyRowSelection";
import { useRowHeight } from "@/hooks/useDensity";
import { useRadarPage } from "@/hooks/useRadarPage";
import { useRealtime } from "@/hooks/useRealtime";
import { useVirtualizedRows } from "@/hooks/useVirtualizedRows";
import type { AnomaliesAggregate } from "@/lib/api/anomalies-types";
import type { RadarItemOut, RadarParams, RadarSortKey } from "@/lib/api/radar-types";
import { formatUtc } from "@/lib/format";

export interface RadarTableProps {
  orgSlug: string;
  initialItems: RadarItemOut[];
  initialCursor: string | null;
  initialAsOf: string;
  hasFilters: boolean;
  /** The exact filters (minus `cursor`) used for the initial server fetch -- reused for "load more" and every reconciliation. */
  baseParams: RadarParams;
  initialAnomalies: AnomaliesAggregate;
}

const OVERSCAN = 8;
const VIEWPORT_HEIGHT = 480;
const HEADER_HEIGHT = 32;
// No real publisher exists yet for `rt:radar` (scanner-worker, T2.5, is only
// a skeleton package) -- this reconciles on a fixed cadence regardless of
// the WS connection state (Astra's T2.7 review: connection health is not
// proof of a live scanner, `services/radar.py`'s `as_of` is only ever the
// query time). A real `rt:radar` message is treated as an opaque
// invalidation signal, never a partial-field merge of an assumed payload
// shape (`.claude/state/notes-T2.7.md`).
const RECONCILE_INTERVAL_MS = 5000;
const RT_RADAR_NOTE = "Nenhum scanner publica eventos em tempo real em rt:radar ainda -- este painel atualiza sozinho a cada 5s.";

function rowId(row: RadarItemOut): string {
  return `radar-row-${row.opportunity_id}`;
}

function loadMoreLabel(hasCursor: boolean, loading: boolean): string {
  if (!hasCursor) return "Fim da lista";
  return loading ? "Carregando..." : "Carregar mais";
}

function ReconcileErrorBanner({ reconcileError }: { reconcileError: string | null }) {
  if (!reconcileError) return null;
  return <p className="text-xs text-warning">Atualização automática falhou: {reconcileError} (mostrando os últimos dados carregados).</p>;
}

/** `/radar`'s table (brief line 9): virtualized, server-filtered/sorted, cursor-paginated, reconciled on an interval since no realtime publisher exists yet. */
export function RadarTable({ orgSlug, initialItems, initialCursor, initialAsOf, hasFilters, baseParams, initialAnomalies }: RadarTableProps) {
  const { getToken } = useAuth();
  const router = useRouter();
  const rowHeight = useRowHeight();
  const [scrollTop, setScrollTop] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);

  const { items, cursor, asOf, anomalies, loadingMore, loadError, reconcileError, reconcile, loadMore } = useRadarPage({
    initialItems,
    initialCursor,
    initialAsOf,
    baseParams,
    initialAnomalies,
  });

  const { startIndex, endIndex, visibleRows, topPad, bottomPad } = useVirtualizedRows({
    rows: items,
    rowHeight,
    scrollTop,
    viewportHeight: VIEWPORT_HEIGHT,
    overscan: OVERSCAN,
  });

  useRealtime({
    channel: "rt:radar",
    enabled: true,
    getAuthToken: () => getToken(),
    onMessage: () => void reconcile(),
  });

  useEffect(() => {
    const id = window.setInterval(() => {
      if (document.visibilityState !== "visible") return;
      void reconcile();
    }, RECONCILE_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, [reconcile]);

  const { selectedIndex, handleKeyDown } = useArrowKeyRowSelection({
    rowCount: items.length,
    rowHeight,
    viewportHeight: VIEWPORT_HEIGHT,
    stickyHeaderHeight: HEADER_HEIGHT,
    getScrollContainer: () => containerRef.current,
    onOpen: (index) => {
      const row = items[index];
      if (row) router.push(`/${orgSlug}/opportunities/${row.opportunity_id}`);
    },
  });

  const selectedRow = selectedIndex >= startIndex && selectedIndex < endIndex ? items[selectedIndex] : undefined;

  function toggleSort(key: RadarSortKey): void {
    const nextOrder = baseParams.sort === key && baseParams.order === "desc" ? "asc" : "desc";
    const params = new URLSearchParams(window.location.search);
    params.set("sort", key);
    params.set("order", nextOrder);
    params.delete("cursor");
    router.push(`${window.location.pathname}?${params.toString()}`);
  }

  if (items.length === 0) return <RadarEmpty orgSlug={orgSlug} hasFilters={hasFilters} />;

  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-fg-muted" title={RT_RADAR_NOTE}>
        Painel consultado {formatUtc(asOf)} · anomalias verificadas {formatUtc(anomalies.asOf)} · uma linha por episódio de oportunidade, não por mercado.
      </p>
      <ReconcileErrorBanner reconcileError={reconcileError} />
      <div className="overflow-x-auto rounded-md border border-border">
        <div
          ref={containerRef}
          onScroll={(e) => setScrollTop(e.currentTarget.scrollTop)}
          onKeyDown={handleKeyDown}
          tabIndex={0}
          role="grid"
          aria-label="Radar de oportunidades"
          aria-activedescendant={selectedRow ? rowId(selectedRow) : undefined}
          aria-rowcount={items.length + 1}
          className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold"
          style={{ height: VIEWPORT_HEIGHT, overflowY: "auto" }}
        >
          <table role="presentation" className="w-full text-left text-[13px]">
            <RadarTableHead sort={baseParams.sort ?? "score"} order={baseParams.order ?? "desc"} onToggleSort={toggleSort} />
            <tbody>
              {topPad > 0 && (
                <tr aria-hidden="true" style={{ height: topPad }}>
                  <td colSpan={RADAR_TABLE_HEADERS.length} />
                </tr>
              )}
              {visibleRows.map((row, visibleOffset) => {
                const absoluteIndex = startIndex + visibleOffset;
                return (
                  <RadarRow
                    key={row.opportunity_id}
                    id={rowId(row)}
                    orgSlug={orgSlug}
                    row={row}
                    anomalies={anomalies.byMarket[row.market_id]}
                    anomaliesUnavailable={anomalies.unavailable}
                    anomaliesTruncated={anomalies.truncated}
                    rowHeight={rowHeight}
                    selected={absoluteIndex === selectedIndex}
                    ariaRowIndex={absoluteIndex + 2}
                    onOpen={() => router.push(`/${orgSlug}/opportunities/${row.opportunity_id}`)}
                  />
                );
              })}
              {bottomPad > 0 && (
                <tr aria-hidden="true" style={{ height: bottomPad }}>
                  <td colSpan={RADAR_TABLE_HEADERS.length} />
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <Button type="button" variant="outline" size="sm" onClick={() => void loadMore()} disabled={!cursor || loadingMore}>
          {loadMoreLabel(cursor !== null, loadingMore)}
        </Button>
        {loadError && <span className="text-xs text-red">{loadError}</span>}
      </div>
      {cursor && (
        <p className="text-[11px] text-fg-subtle">
          Paginação sobre um ranking que muda continuamente: uma oportunidade ainda não vista pode não aparecer mais adiante se o score dela mudar entre páginas.
        </p>
      )}
    </div>
  );
}
