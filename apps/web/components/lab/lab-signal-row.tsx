"use client";

import { LabAsOf } from "@/components/lab/lab-as-of";
import { formatPrice } from "@/components/markets/format";
import { LabMarketLink } from "@/components/lab/lab-market-link";
import { ResultChip, TrackingStateChip } from "@/components/lab/lab-signal-chips";
import { formatR, signColorClass } from "@/components/lab/lab-format";
import type { SignalListItemOut } from "@/lib/api/lab-types";
import { cn } from "@/lib/utils";

export interface LabSignalRowProps {
  id: string;
  orgSlug: string;
  row: SignalListItemOut;
  versionLabel: string;
  rowHeight: number;
  selected: boolean;
  ariaRowIndex: number;
  onOpen: () => void;
}

const SECONDARY_CELL = "hidden px-3 text-right font-mono tabular-nums text-fg-muted lg:table-cell";

/** One row of the Shadow Lab signals table -- essential columns visible on mobile (decision_at, mercado, chips, r_multiple), the rest secondary (docs/DESIGN.md §2). */
export function LabSignalRow({ id, orgSlug, row, versionLabel, rowHeight, selected, ariaRowIndex, onOpen }: LabSignalRowProps) {
  const r = formatR(row.r_multiple, row.r_multiple_reason);
  const rExFunding = row.r_ex_funding;

  return (
    <tr
      id={id}
      role="row"
      aria-rowindex={ariaRowIndex}
      aria-selected={selected}
      style={{ height: rowHeight }}
      className={cn("cursor-pointer border-t border-border hover:bg-bg-overlay", selected && "bg-bg-overlay ring-1 ring-inset ring-gold")}
      onClick={onOpen}
    >
      <td role="gridcell" className="px-3 text-xs">
        <LabAsOf iso={row.decision_at} />
      </td>
      <td role="gridcell" className="px-3">
        <LabMarketLink orgSlug={orgSlug} symbol={row.market} />
      </td>
      <td role="gridcell" className="hidden px-3 text-xs text-fg-muted lg:table-cell">
        {versionLabel}
      </td>
      <td role="gridcell" className={SECONDARY_CELL}>{formatPrice(row.reference_price)}</td>
      <td role="gridcell" className={SECONDARY_CELL}>{formatPrice(row.stop)}</td>
      <td role="gridcell" className={SECONDARY_CELL}>{formatPrice(row.target1)}</td>
      <td role="gridcell" className={SECONDARY_CELL}>{formatPrice(row.virtual_entry)}</td>
      <td role="gridcell" className="px-3">
        <TrackingStateChip state={row.tracking_state} reason={row.no_entry_reason ?? row.censored_reason} />
      </td>
      <td role="gridcell" className="px-3">
        <ResultChip result={row.result} />
      </td>
      <td role="gridcell" className={cn("px-3 text-right font-mono tabular-nums", r.isValue ? signColorClass(row.r_multiple) : "text-fg-muted")}>
        {r.text}
      </td>
      <td role="gridcell" className={cn(SECONDARY_CELL, rExFunding !== null && signColorClass(rExFunding))}>
        {rExFunding !== null ? `${rExFunding}R` : "--"}
      </td>
    </tr>
  );
}
