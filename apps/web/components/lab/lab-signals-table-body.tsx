"use client";

import { LabSignalRow } from "@/components/lab/lab-signal-row";
import { LAB_SEGMENT_LABEL, type LabSegment } from "@/components/lab/lab-signal-segments";
import type { MoneyRuler } from "@/components/lab/lab-money";
import type { SignalListItemOut } from "@/lib/api/lab-types";

export interface LabSignalsTableBodyProps {
  orgSlug: string;
  visibleItems: SignalListItemOut[];
  visibleRows: SignalListItemOut[];
  startIndex: number;
  topPad: number;
  bottomPad: number;
  colSpan: number;
  segment: LabSegment;
  versionLabelFor: (id: string) => string;
  ruler: MoneyRuler;
  showResearch: boolean;
  rowHeight: number;
  selectedIndex: number;
  panelOpen: boolean;
  rowIdFor: (row: SignalListItemOut) => string;
  onOpenRow: (row: SignalListItemOut) => void;
}

/**
 * `LabSignalsTable`'s `<tbody>` -- either the segment's own honest empty
 * state (brief T3.17b item 4: a segment with no rows never reuses the
 * whole-table "0 sinais" empty state, which would misreport an empty
 * *selection* as an empty *Lab*) or the virtualized window of rows. Split out
 * so `LabSignalsTable` itself stays under the lint config's
 * cyclomatic-complexity budget.
 */
export function LabSignalsTableBody({
  orgSlug,
  visibleItems,
  visibleRows,
  startIndex,
  topPad,
  bottomPad,
  colSpan,
  segment,
  versionLabelFor,
  ruler,
  showResearch,
  rowHeight,
  selectedIndex,
  panelOpen,
  rowIdFor,
  onOpenRow,
}: LabSignalsTableBodyProps) {
  if (visibleItems.length === 0) {
    return (
      <tbody>
        <tr>
          <td colSpan={colSpan} className="p-6 text-center text-sm text-fg-muted">
            Nenhum sinal em &quot;{LAB_SEGMENT_LABEL[segment]}&quot; nesta seleção -- troque de guia para ver os demais.
          </td>
        </tr>
      </tbody>
    );
  }

  return (
    <tbody>
      {topPad > 0 && (
        <tr aria-hidden="true" style={{ height: topPad }}>
          <td colSpan={colSpan} />
        </tr>
      )}
      {visibleRows.map((row, visibleOffset) => {
        const absoluteIndex = startIndex + visibleOffset;
        return (
          <LabSignalRow
            key={row.signal_id}
            id={rowIdFor(row)}
            orgSlug={orgSlug}
            row={row}
            versionLabel={versionLabelFor(row.strategy_version_id)}
            ruler={ruler}
            showResearch={showResearch}
            rowHeight={rowHeight}
            selected={absoluteIndex === selectedIndex}
            ariaRowIndex={absoluteIndex + 2}
            panelOpen={panelOpen}
            onOpen={() => onOpenRow(row)}
          />
        );
      })}
      {bottomPad > 0 && (
        <tr aria-hidden="true" style={{ height: bottomPad }}>
          <td colSpan={colSpan} />
        </tr>
      )}
    </tbody>
  );
}
