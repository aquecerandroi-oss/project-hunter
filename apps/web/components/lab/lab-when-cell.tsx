"use client";

import { useEffect, useState } from "react";

import { formatWhenShort } from "@/components/lab/lab-format";
import { formatLocalOffset } from "@/lib/format";

export interface WhenCellProps {
  iso: string | null;
  /**
   * Appends " UTC" to the visible text -- the "Quando" column's own literal
   * example (brief T3.17b item 3: "08/09 05:05 UTC"). Entry/exit cells pass
   * `false` to save width (the row's own "Quando" cell already anchors the
   * day; a bare "08/09 05:26" next to a price reads as its time, not a
   * second, unrelated instant).
   */
  suffix?: boolean;
  className?: string;
}

/**
 * One-line date+time, fixed width so it never wraps (brief T3.17b item 3:
 * "05:05:05 UTC (02:05:05 -03:00)" -- the previous text -- had no date at
 * all and wrapped across four lines, so two different days looked
 * identical on screen). The full ISO instant and the local wall-clock time
 * both stay one hover away in a single `title` tooltip, computed
 * client-side after mount (H2, mirrors `LabAsOf`): the local half depends on
 * the *browser's* own timezone, so baking it in during SSR (a UTC container)
 * would show every visitor's own local time as `+00:00`.
 */
export function WhenCell({ iso, suffix = true, className }: WhenCellProps) {
  const [title, setTitle] = useState<string | undefined>(iso ?? undefined);

  useEffect(() => {
    if (iso === null) return;
    const local = formatLocalOffset(iso);
    // eslint-disable-next-line react-hooks/set-state-in-effect -- syncing from the runtime's own timezone, an external system, once mounted (H2)
    setTitle(local ? `${iso} (local ${local})` : iso);
  }, [iso]);

  const fallbackClass = className ?? "whitespace-nowrap font-mono tabular-nums";
  if (iso === null) return <span className={fallbackClass}>--</span>;

  const short = formatWhenShort(iso);
  if (short === null) return <span className={fallbackClass}>--</span>;

  return (
    <span title={title} className={fallbackClass}>
      {suffix ? `${short} UTC` : short}
    </span>
  );
}
