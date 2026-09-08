"use client";

import { LabSignalRow } from "@/components/lab/lab-signal-row";
import type { LabSignalGroup } from "@/components/lab/lab-signal-grouping";
import { LAB_SEGMENT_LABEL, type LabSegment } from "@/components/lab/lab-signal-segments";
import type { MoneyRuler } from "@/components/lab/lab-money";
import type { LabVersionChip } from "@/components/lab/lab-strategy-cell";

export interface LabSignalsTableBodyProps {
  orgSlug: string;
  visibleGroups: LabSignalGroup[];
  visibleRows: LabSignalGroup[];
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
  rowIdFor: (group: LabSignalGroup) => string;
  onOpenRow: (group: LabSignalGroup) => void;
}

/** One group's chips (brief T3.38) -- `undefined` (renders the plain `LabStrategyCell`) unless the group actually spans more than one version. */
function chipsFor(group: LabSignalGroup, versionLabelFor: (id: string) => string): LabVersionChip[] | undefined {
  if (group.versionIds.length <= 1) return undefined;
  return group.versionIds.map((versionId) => {
    const member = group.members.find((m) => m.strategy_version_id === versionId);
    return { versionId, label: versionLabelFor(versionId), purpose: member?.purpose ?? "" };
  });
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
  visibleGroups,
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
  if (visibleGroups.length === 0) {
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
      {visibleRows.map((group, visibleOffset) => {
        const absoluteIndex = startIndex + visibleOffset;
        return (
          <LabSignalRow
            key={group.key}
            id={rowIdFor(group)}
            orgSlug={orgSlug}
            row={group.primary}
            versionLabel={versionLabelFor(group.primary.strategy_version_id)}
            versionChips={chipsFor(group, versionLabelFor)}
            members={group.members}
            ruler={ruler}
            showResearch={showResearch}
            rowHeight={rowHeight}
            selected={absoluteIndex === selectedIndex}
            ariaRowIndex={absoluteIndex + 2}
            panelOpen={panelOpen}
            onOpen={() => onOpenRow(group)}
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
