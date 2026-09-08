"use client";

import { useMemo, useRef, useState } from "react";

import { LabSignalPanel } from "@/components/lab/lab-signal-panel";
import { groupSignalsByIdentity, type LabSignalGroup } from "@/components/lab/lab-signal-grouping";
import { LabSignalsTableBody } from "@/components/lab/lab-signals-table-body";
import { labSignalsHeaders, LabSignalsTableHead } from "@/components/lab/lab-signals-table-head";
import type { LabSegment } from "@/components/lab/lab-signal-segments";
import type { MoneyRuler } from "@/components/lab/lab-money";
import { useArrowKeyRowSelection } from "@/hooks/useArrowKeyRowSelection";
import { useRowHeight } from "@/hooks/useDensity";
import { useVirtualizedRows } from "@/hooks/useVirtualizedRows";
import type { SignalListItemOut } from "@/lib/api/lab-types";

export interface LabSignalsGridProps {
  orgSlug: string;
  items: SignalListItemOut[];
  versionLabelFor: (id: string) => string;
  ruler: MoneyRuler;
  showResearch: boolean;
  segment: LabSegment;
}

const OVERSCAN = 8;
const VIEWPORT_HEIGHT = 480;
const HEADER_HEIGHT = 32;

function rowId(group: LabSignalGroup): string {
  return `lab-signal-row-${group.primary.signal_id}`;
}

/**
 * The virtualized grid + its own side detail panel (T3.37, split out of
 * `LabSignalsTable`): mounted with `key={state-page.from-pageSize}` by its
 * caller, so a new page's own scroll position/selection start fresh through
 * a normal fresh mount instead of an effect calling `setState` on every page
 * change (the React team's own guidance -- "you might not need an effect" --
 * which this codebase's lint config enforces as an error,
 * `react-hooks/set-state-in-effect`).
 */
export function LabSignalsGrid({ orgSlug, items, versionLabelFor, ruler, showResearch, segment }: LabSignalsGridProps) {
  const rowHeight = useRowHeight();
  const [scrollTop, setScrollTop] = useState(0);
  const [selectedGroup, setSelectedGroup] = useState<LabSignalGroup | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const headers = labSignalsHeaders(showResearch);

  // Sibling-version signals that decided the exact same operation collapse
  // into one visual row here (brief T3.38) -- purely presentational, scoped
  // to this one loaded page (`items` never spans a page boundary).
  const groups = useMemo(() => groupSignalsByIdentity(items), [items]);

  const { startIndex, endIndex, visibleRows, topPad, bottomPad } = useVirtualizedRows({
    rows: groups,
    rowHeight,
    scrollTop,
    viewportHeight: VIEWPORT_HEIGHT,
    overscan: OVERSCAN,
  });

  const { selectedIndex, handleKeyDown } = useArrowKeyRowSelection({
    rowCount: groups.length,
    rowHeight,
    viewportHeight: VIEWPORT_HEIGHT,
    stickyHeaderHeight: HEADER_HEIGHT,
    getScrollContainer: () => containerRef.current,
    onOpen: (index) => setSelectedGroup(groups[index] ?? null),
  });

  const selectedRow = selectedIndex >= startIndex && selectedIndex < endIndex ? groups[selectedIndex] : undefined;

  return (
    <div className="flex flex-col gap-3 lg:flex-row">
      <div className="flex flex-1 flex-col gap-2">
        <div className="rounded-md border border-border lg:overflow-x-visible">
          <div
            ref={containerRef}
            onScroll={(e) => setScrollTop(e.currentTarget.scrollTop)}
            onKeyDown={handleKeyDown}
            tabIndex={0}
            role="grid"
            aria-label="Sinais do Shadow Lab"
            aria-activedescendant={selectedRow ? rowId(selectedRow) : undefined}
            aria-rowcount={groups.length + 1}
            className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold"
            style={{ height: VIEWPORT_HEIGHT, overflowY: "auto" }}
          >
            <table role="presentation" className="w-full text-left text-[13px]">
              <LabSignalsTableHead showResearch={showResearch} panelOpen={selectedGroup !== null} />
              <LabSignalsTableBody
                orgSlug={orgSlug}
                visibleGroups={groups}
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
                panelOpen={selectedGroup !== null}
                rowIdFor={rowId}
                onOpenRow={setSelectedGroup}
              />
            </table>
          </div>
        </div>
      </div>
      <div className="lg:w-80 xl:w-96">
        <LabSignalPanel
          signal={selectedGroup?.primary ?? null}
          versionLabel={selectedGroup ? versionLabelFor(selectedGroup.primary.strategy_version_id) : ""}
          ruler={ruler}
          siblingSignals={selectedGroup?.members ?? []}
          versionLabelFor={versionLabelFor}
        />
      </div>
    </div>
  );
}
