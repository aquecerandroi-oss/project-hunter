"use client";

import { LAB_SEGMENT_LABEL, LAB_SEGMENTS, segmentCounts, type LabSegment } from "@/components/lab/lab-signal-segments";
import type { SignalListItemOut } from "@/lib/api/lab-types";
import { cn } from "@/lib/utils";

export interface LabSegmentTabsProps {
  rows: SignalListItemOut[];
  value: LabSegment;
  onChange: (segment: LabSegment) => void;
}

/** "Concluídas · Abertas · Pendentes/sem entrada · Todas" (brief T3.17b item 4), each with the count among the rows currently loaded. */
export function LabSegmentTabs({ rows, value, onChange }: LabSegmentTabsProps) {
  const counts = segmentCounts(rows);
  return (
    <div role="tablist" aria-label="Filtrar sinais por estado" className="flex flex-wrap gap-1">
      {LAB_SEGMENTS.map((segment) => (
        <button
          key={segment}
          type="button"
          role="tab"
          aria-selected={value === segment}
          onClick={() => onChange(segment)}
          className={cn(
            "rounded-md border px-2.5 py-1 text-xs font-medium transition-colors",
            value === segment ? "border-gold bg-gold-soft text-gold" : "border-border text-fg-muted hover:text-fg",
          )}
        >
          {LAB_SEGMENT_LABEL[segment]} ({counts[segment]})
        </button>
      ))}
    </div>
  );
}
