"use client";

import { useMemo, useRef, useState } from "react";

import { LabSignalPanel } from "@/components/lab/lab-signal-panel";
import { LabSignalRow } from "@/components/lab/lab-signal-row";
import { LabSignalsEmpty } from "@/components/lab/lab-signals-empty";
import { LAB_SIGNALS_HEADERS, LabSignalsTableHead } from "@/components/lab/lab-signals-table-head";
import { Button } from "@/components/ui/button";
import { useArrowKeyRowSelection } from "@/hooks/useArrowKeyRowSelection";
import { useRowHeight } from "@/hooks/useDensity";
import { useVirtualizedRows } from "@/hooks/useVirtualizedRows";
import { loadLabSignalsAction } from "@/lib/api/lab-actions";
import type { LabSignalsParams } from "@/lib/api/lab";
import type { SignalListItemOut } from "@/lib/api/lab-types";
import { logger } from "@/lib/logger";

export interface LabSignalsTableProps {
  orgSlug: string;
  initialItems: SignalListItemOut[];
  initialCursor: string | null;
  /** Filters already applied server-side to `initialItems` -- reused for every "load more" page so the cursor keeps scanning the same, stable selection. */
  baseParams: LabSignalsParams;
  versionLabelById: Record<string, string>;
  cohort: string;
}

const OVERSCAN = 8;
const VIEWPORT_HEIGHT = 480;
const HEADER_HEIGHT = 32;

function rowId(row: SignalListItemOut): string {
  return `lab-signal-row-${row.signal_id}`;
}

/**
 * `/lab`'s signals list: virtualized (brief S3b, mirrors
 * `components/markets/markets-table.tsx`), cursor-paginated via a Server
 * Action (`load more`, never a client-side call into `@/lib/server/**`),
 * with a side detail panel instead of per-row accordions (keeps every row
 * the same height, which the virtualization math requires).
 *
 * This endpoint does not accept `window`/`as_of` (contract-S3-lab.md) --
 * said explicitly below so it never looks like it shares the summary's
 * clock (Astra, S3b hierarchy review, must-fix).
 */
export function LabSignalsTable({ orgSlug, initialItems, initialCursor, baseParams, versionLabelById, cohort }: LabSignalsTableProps) {
  const rowHeight = useRowHeight();
  const [items, setItems] = useState(initialItems);
  const [cursor, setCursor] = useState(initialCursor);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [selectedSignal, setSelectedSignal] = useState<SignalListItemOut | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

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
    onOpen: (index) => setSelectedSignal(items[index] ?? null),
  });

  const selectedRow = selectedIndex >= startIndex && selectedIndex < endIndex ? items[selectedIndex] : undefined;

  async function loadMore(): Promise<void> {
    if (!cursor || loadingMore) return;
    setLoadingMore(true);
    setLoadError(null);
    try {
      const outcome = await loadLabSignalsAction({ ...baseParams, cursor });
      if (!outcome.ok) {
        setLoadError(outcome.reason ?? "erro desconhecido");
        return;
      }
      setItems((prev) => [...prev, ...outcome.page.items]);
      setCursor(outcome.page.next_cursor);
    } catch (error) {
      logger.error("lab_signals_load_more_failed", { error: String(error) });
      setLoadError("falha ao carregar mais sinais");
    } finally {
      setLoadingMore(false);
    }
  }

  const versionLabelFor = useMemo(
    () => (id: string) => versionLabelById[id] ?? id,
    [versionLabelById],
  );

  if (items.length === 0) return <LabSignalsEmpty cohort={cohort} />;

  return (
    <div className="flex flex-col gap-3 lg:flex-row">
      <div className="flex flex-1 flex-col gap-2">
        <p className="text-xs text-fg-muted">
          Sinais · todo o período disponível (este endpoint não aceita janela/`as_of` -- só o resumo acima é filtrado por
          janela).
        </p>
        <div className="overflow-x-auto rounded-md border border-border">
          <div
            ref={containerRef}
            onScroll={(e) => setScrollTop(e.currentTarget.scrollTop)}
            onKeyDown={handleKeyDown}
            tabIndex={0}
            role="grid"
            aria-label="Sinais do Shadow Lab"
            aria-activedescendant={selectedRow ? rowId(selectedRow) : undefined}
            aria-rowcount={items.length + 1}
            className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold"
            style={{ height: VIEWPORT_HEIGHT, overflowY: "auto" }}
          >
            <table role="presentation" className="w-full text-left text-[13px]">
              <LabSignalsTableHead />
              <tbody>
                {topPad > 0 && (
                  <tr aria-hidden="true" style={{ height: topPad }}>
                    <td colSpan={LAB_SIGNALS_HEADERS.length} />
                  </tr>
                )}
                {visibleRows.map((row, visibleOffset) => {
                  const absoluteIndex = startIndex + visibleOffset;
                  return (
                    <LabSignalRow
                      key={row.signal_id}
                      id={rowId(row)}
                      orgSlug={orgSlug}
                      row={row}
                      versionLabel={versionLabelFor(row.strategy_version_id)}
                      rowHeight={rowHeight}
                      selected={absoluteIndex === selectedIndex}
                      ariaRowIndex={absoluteIndex + 2}
                      onOpen={() => setSelectedSignal(row)}
                    />
                  );
                })}
                {bottomPad > 0 && (
                  <tr aria-hidden="true" style={{ height: bottomPad }}>
                    <td colSpan={LAB_SIGNALS_HEADERS.length} />
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
      <div className="lg:w-96">
        <LabSignalPanel
          signal={selectedSignal}
          versionLabel={selectedSignal ? versionLabelFor(selectedSignal.strategy_version_id) : ""}
        />
      </div>
    </div>
  );
}
