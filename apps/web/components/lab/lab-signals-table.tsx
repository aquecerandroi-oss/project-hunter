"use client";

import { useMemo, useRef, useState } from "react";

import { LabLoadMore } from "@/components/lab/lab-load-more";
import { LabSegmentTabs } from "@/components/lab/lab-segment-tabs";
import { LabSignalPanel } from "@/components/lab/lab-signal-panel";
import { LabSignalsEmpty } from "@/components/lab/lab-signals-empty";
import { LabSignalsTableBody } from "@/components/lab/lab-signals-table-body";
import { labSignalsHeaders, LabSignalsTableHead } from "@/components/lab/lab-signals-table-head";
import { visibleSignalsForSegment, type LabSegment } from "@/components/lab/lab-signal-segments";
import { LabTotalsCard } from "@/components/lab/lab-totals-card";
import type { MoneyRuler } from "@/components/lab/lab-money";
import { Button } from "@/components/ui/button";
import { useArrowKeyRowSelection } from "@/hooks/useArrowKeyRowSelection";
import { useRowHeight } from "@/hooks/useDensity";
import { useVirtualizedRows } from "@/hooks/useVirtualizedRows";
import { loadLabSignalsAction } from "@/lib/api/lab-actions";
import type { LabSignalsParams } from "@/lib/api/lab";
import type { SignalListItemOut } from "@/lib/api/lab-types";
import { logger } from "@/lib/logger";

/** The endpoint-scope fact that used to sit as a plain paragraph above the table (brief T3.17b item 2: it read as a technical leak into the UI) -- now one hover away on the period label instead. */
const PERIOD_TOOLTIP =
  "período: todo o disponível — este endpoint não aceita janela/as_of; só o resumo acima é filtrado por janela.";

export interface LabSignalsTableProps {
  orgSlug: string;
  initialItems: SignalListItemOut[];
  initialCursor: string | null;
  /** Filters already applied server-side to `initialItems` -- reused for every "load more" page so the cursor keeps scanning the same, stable selection. */
  baseParams: LabSignalsParams;
  versionLabelById: Record<string, string>;
  cohort: string;
  ruler: MoneyRuler;
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
export function LabSignalsTable({ orgSlug, initialItems, initialCursor, baseParams, versionLabelById, cohort, ruler }: LabSignalsTableProps) {
  const rowHeight = useRowHeight();
  const [items, setItems] = useState(initialItems);
  const [cursor, setCursor] = useState(initialCursor);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [selectedSignal, setSelectedSignal] = useState<SignalListItemOut | null>(null);
  const [showResearch, setShowResearch] = useState(false);
  // Default "Concluídas" (brief T3.17b item 4): Everton's own screenshot
  // showed a fresh page of mostly-pending rows pushing every concluded
  // operation off the first screen -- the segment a reader actually wants to
  // see first is the one with a settled result.
  const [segment, setSegment] = useState<LabSegment>("concluded");
  const containerRef = useRef<HTMLDivElement>(null);
  const headers = labSignalsHeaders(showResearch);

  const visibleItems = useMemo(() => visibleSignalsForSegment(items, segment), [items, segment]);

  const { startIndex, endIndex, visibleRows, topPad, bottomPad } = useVirtualizedRows({
    rows: visibleItems,
    rowHeight,
    scrollTop,
    viewportHeight: VIEWPORT_HEIGHT,
    overscan: OVERSCAN,
  });

  const { selectedIndex, handleKeyDown, reset: resetSelection } = useArrowKeyRowSelection({
    rowCount: visibleItems.length,
    rowHeight,
    viewportHeight: VIEWPORT_HEIGHT,
    stickyHeaderHeight: HEADER_HEIGHT,
    getScrollContainer: () => containerRef.current,
    onOpen: (index) => setSelectedSignal(visibleItems[index] ?? null),
  });

  const selectedRow = selectedIndex >= startIndex && selectedIndex < endIndex ? visibleItems[selectedIndex] : undefined;

  function handleSegmentChange(next: LabSegment): void {
    setSegment(next);
    setScrollTop(0);
    resetSelection();
  }

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
    <div className="flex flex-col gap-4">
      <LabTotalsCard rows={items} ruler={ruler} hasMore={cursor !== null} />
      <div className="flex flex-col gap-3 lg:flex-row">
        <div className="flex flex-1 flex-col gap-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="cursor-help text-xs text-fg-muted underline decoration-dotted underline-offset-2" title={PERIOD_TOOLTIP}>
              período: todo o disponível
            </span>
            <Button type="button" variant="outline" size="sm" aria-pressed={showResearch} onClick={() => setShowResearch((v) => !v)}>
              {showResearch ? "Ocultar detalhes de pesquisa" : "Detalhes de pesquisa"}
            </Button>
          </div>
          <LabSegmentTabs rows={items} value={segment} onChange={handleSegmentChange} />
          <div className="overflow-x-auto rounded-md border border-border">
            <div
              ref={containerRef}
              onScroll={(e) => setScrollTop(e.currentTarget.scrollTop)}
              onKeyDown={handleKeyDown}
              tabIndex={0}
              role="grid"
              aria-label="Sinais do Shadow Lab"
              aria-activedescendant={selectedRow ? rowId(selectedRow) : undefined}
              aria-rowcount={visibleItems.length + 1}
              className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold"
              style={{ height: VIEWPORT_HEIGHT, overflowY: "auto" }}
            >
              <table role="presentation" className="w-full min-w-max text-left text-[13px]">
                <LabSignalsTableHead showResearch={showResearch} />
                <LabSignalsTableBody
                  orgSlug={orgSlug}
                  visibleItems={visibleItems}
                  visibleRows={visibleRows}
                  startIndex={startIndex}
                  topPad={topPad}
                  bottomPad={bottomPad}
                  colSpan={headers.length}
                  segment={segment}
                  versionLabelFor={versionLabelFor}
                  ruler={ruler}
                  showResearch={showResearch}
                  rowHeight={rowHeight}
                  selectedIndex={selectedIndex}
                  rowIdFor={rowId}
                  onOpenRow={setSelectedSignal}
                />
              </table>
            </div>
          </div>
          <LabLoadMore cursor={cursor} loadingMore={loadingMore} loadError={loadError} onLoadMore={() => void loadMore()} />
        </div>
        <div className="lg:w-96">
          <LabSignalPanel
            signal={selectedSignal}
            versionLabel={selectedSignal ? versionLabelFor(selectedSignal.strategy_version_id) : ""}
            ruler={ruler}
          />
        </div>
      </div>
    </div>
  );
}
