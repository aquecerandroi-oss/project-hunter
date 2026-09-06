"use client";

import { useEffect, useState } from "react";

import { formatLocalOffset, formatUtc } from "@/lib/format";

export interface LabAsOfProps {
  iso: string;
}

/**
 * UTC + local offset (docs/DESIGN.md joint decision #9), client-only for the
 * local half (H2, mirrors `components/markets/recent-trades.tsx`'s
 * `useTradeTimestampText`): the server container runs UTC, so computing the
 * runtime's own offset during SSR would bake in "+00:00" for every visitor
 * instead of their real timezone -- never a hydration mismatch (this file
 * has no server-rendered counterpart to diverge from), just wrong data if
 * done eagerly. `formatUtc` alone is deterministic everywhere and renders
 * immediately; the offset appends one render after mount.
 */
export function LabAsOf({ iso }: LabAsOfProps) {
  const [local, setLocal] = useState<string | null>(null);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- syncing from the runtime's own timezone, an external system, once mounted (H2)
    setLocal(formatLocalOffset(iso));
  }, [iso]);

  const utc = formatUtc(iso);
  return <span className="font-mono tabular-nums">{local ? `${utc} (${local})` : utc}</span>;
}
