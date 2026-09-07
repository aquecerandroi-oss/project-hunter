"use client";

import { useEffect, useState } from "react";

import { formatLocalOffset, formatUtc } from "@/lib/format";

export interface PortfolioAsOfProps {
  iso: string;
}

/**
 * UTC + local offset (docs/DESIGN.md joint decision #9), client-only for the
 * local half -- mirrors `components/lab/lab-as-of.tsx` exactly, and for the
 * same reason (H2): a Server Component on this screen (`PortfolioHeader`,
 * `PortfolioResultCard`, `PortfolioProposalsEmpty`) can render this Client
 * Component directly, but calling `formatUtcWithOffset` straight from a
 * Server Component would bake in the SERVER CONTAINER's own timezone (always
 * UTC in this stack) as if it were the operator's local time -- not a
 * hydration mismatch there (a Server Component never re-executes on the
 * client), but silently wrong data. `formatUtc` alone is deterministic
 * everywhere and renders immediately; the real local offset is only knowable
 * once this runs in the operator's own browser, after mount.
 */
export function PortfolioAsOf({ iso }: PortfolioAsOfProps) {
  const [local, setLocal] = useState<string | null>(null);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- syncing from the runtime's own timezone, an external system, once mounted (H2)
    setLocal(formatLocalOffset(iso));
  }, [iso]);

  const utc = formatUtc(iso);
  return <span className="font-mono tabular-nums">{local ? `${utc} (${local})` : utc}</span>;
}
