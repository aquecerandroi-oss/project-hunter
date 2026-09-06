"use client";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { formatDecimalOrReason, signColorClass } from "@/components/lab/lab-format";

export interface LabMetricItemProps {
  label: string;
  definition: string;
  value: string | null;
  reason: string | null;
  suffix?: string;
  /** Extra detail always shown under the value, e.g. PF's `sum_positive/sum_negative_abs/sample_size` or the R sum's `count`/`ordered_by` -- never hidden inside the tooltip (brief S3b: "visíveis"). */
  detail?: string;
}

/**
 * One metric cell: label, value (or its reason, never a `0`/dash), and a
 * focus-visible tooltip with the metric's exact definition (brief S3b).
 * Colored green/red only when there IS a real signed value; a reason string
 * is neutral text, never colored as if it were a number (mirrors
 * `MarketRow`'s "absent data is never painted positive" rule).
 */
export function LabMetricItem({ label, definition, value, reason, suffix = "", detail }: LabMetricItemProps) {
  const { text, isValue } = formatDecimalOrReason(value, reason, suffix);
  return (
    <div className="flex flex-col gap-0.5">
      <Tooltip>
        <TooltipTrigger asChild>
          <button type="button" className="w-fit text-left text-xs text-fg-muted underline decoration-dotted underline-offset-2">
            {label}
          </button>
        </TooltipTrigger>
        <TooltipContent>{definition}</TooltipContent>
      </Tooltip>
      <span className={`font-mono text-base tabular-nums ${isValue ? signColorClass(value) : "text-fg-muted"}`}>
        {text}
      </span>
      {detail && <span className="text-[11px] text-fg-subtle">{detail}</span>}
    </div>
  );
}
