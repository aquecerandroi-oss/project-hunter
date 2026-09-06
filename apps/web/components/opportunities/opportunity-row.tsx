"use client";

import Link from "next/link";

import { InPositionChip, RegimeChip, RiskBlockedChip, StageChip, StatusChip } from "@/components/radar/status-chip";
import { formatUtc } from "@/lib/format";
import type { OpportunitySummaryOut } from "@/lib/api/opportunities-types";
import { cn } from "@/lib/utils";

export interface OpportunityRowProps {
  id: string;
  orgSlug: string;
  row: OpportunitySummaryOut;
  rowHeight: number;
  selected?: boolean;
  ariaRowIndex: number;
  onOpen?: () => void;
}

/** One row of `/opportunities` -- the compact index; the full "why" lives only at `/opportunities/[id]` (Astra's T2.7 review). */
export function OpportunityRow({ id, orgSlug, row, rowHeight, selected = false, ariaRowIndex, onOpen }: OpportunityRowProps) {
  return (
    <tr
      id={id}
      role="row"
      aria-rowindex={ariaRowIndex}
      aria-selected={selected}
      style={{ height: rowHeight }}
      className={cn("cursor-pointer border-t border-border hover:bg-bg-overlay", selected && "bg-bg-overlay ring-1 ring-inset ring-gold")}
      onClick={(event) => {
        if ((event.target as HTMLElement).closest("a, button")) return;
        onOpen?.();
      }}
    >
      <td role="gridcell" className="px-3">
        <Link href={`/${orgSlug}/opportunities/${row.id}`} className="font-medium text-fg hover:text-gold">
          {row.symbol}
        </Link>
        <span className="ml-1.5 text-[11px] text-fg-subtle">{row.exchange}</span>
        <div className="mt-0.5 flex flex-wrap gap-1">
          <InPositionChip inPosition={row.in_position} />
          <RiskBlockedChip riskBlocked={row.risk_blocked} />
        </div>
      </td>
      <td role="gridcell" className="px-3 text-right font-mono text-sm tabular-nums text-fg">
        {row.score}
      </td>
      <td role="gridcell" className="px-3">
        <StatusChip status={row.status} />
      </td>
      <td role="gridcell" className="px-3">
        <StageChip stage={row.stage} />
      </td>
      <td role="gridcell" className="px-3">
        <RegimeChip regime={row.regime} />
      </td>
      <td role="gridcell" className="hidden px-3 text-right font-mono text-xs tabular-nums text-fg-muted md:table-cell">
        {formatUtc(row.last_updated_at)}
      </td>
    </tr>
  );
}
