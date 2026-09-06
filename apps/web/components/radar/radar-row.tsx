"use client";

import Link from "next/link";

import { AnomalyCountCell, type RadarAnomalySummary } from "@/components/radar/anomaly-count-cell";
import { QualityCell } from "@/components/radar/quality-cell";
import { ScoreCell } from "@/components/radar/score-cell";
import { InPositionChip, RegimeChip, RiskBlockedChip, StageChip, StatusChip } from "@/components/radar/status-chip";
import { computeAgeMs, formatAge, useAgeTicker } from "@/hooks/useAgeTicker";
import type { RadarItemOut } from "@/lib/api/radar-types";
import { cn } from "@/lib/utils";

export interface RadarRowProps {
  id: string;
  orgSlug: string;
  row: RadarItemOut;
  anomalies: RadarAnomalySummary[] | undefined;
  anomaliesUnavailable: boolean;
  anomaliesTruncated: boolean;
  rowHeight: number;
  selected?: boolean;
  ariaRowIndex: number;
  onOpen?: () => void;
}

/** One row of `/radar` -- one scored opportunity episode, the whole row clickable to `/opportunities/[id]` (brief line 9). */
export function RadarRow({
  id,
  orgSlug,
  row,
  anomalies,
  anomaliesUnavailable,
  anomaliesTruncated,
  rowHeight,
  selected = false,
  ariaRowIndex,
  onOpen,
}: RadarRowProps) {
  const now = useAgeTicker();
  const ageMs = computeAgeMs(row.first_seen_at, now);
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
        <Link href={`/${orgSlug}/markets/${encodeURIComponent(row.exchange)}/${encodeURIComponent(row.symbol)}`} className="font-medium text-fg hover:text-gold">
          {row.symbol}
        </Link>
        <span className="ml-1.5 text-[11px] text-fg-subtle">{row.exchange}</span>
        <div className="mt-0.5 flex flex-wrap gap-1">
          <InPositionChip inPosition={row.in_position} />
          <RiskBlockedChip riskBlocked={row.risk_blocked} reason={row.risk_blocked_reason ?? null} />
        </div>
      </td>
      <td role="gridcell" className="px-3 text-right">
        <ScoreCell score={row.score} change={row.change} firstSeenAt={row.first_seen_at} lastUpdatedAt={row.last_updated_at} />
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
      <td role="gridcell" className="px-3">
        <QualityCell confidence={row.confidence} lastUpdatedAt={row.last_updated_at} />
      </td>
      <td role="gridcell" className="hidden px-3 md:table-cell">
        <AnomalyCountCell anomalies={anomalies} unavailable={anomaliesUnavailable} truncated={anomaliesTruncated} />
      </td>
      <td role="gridcell" className="hidden px-3 text-right font-mono text-xs tabular-nums text-fg-muted md:table-cell">
        {ageMs !== null ? formatAge(ageMs) : "—"}
      </td>
    </tr>
  );
}
