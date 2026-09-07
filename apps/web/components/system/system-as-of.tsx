"use client";

import { useEffect, useState } from "react";

import { formatLocalOffset, formatUtc } from "@/lib/format";

export interface SystemAsOfProps {
  iso: string;
}

/**
 * UTC + local offset (docs/DESIGN.md joint decision #9), client-only for the
 * local half -- mirrors `components/portfolio/portfolio-as-of.tsx` and
 * `components/lab/lab-as-of.tsx` exactly, and for the same reason (H2): this
 * domain (`system/`) keeps its own copy rather than importing another
 * screen's component, same convention as those two siblings duplicating
 * instead of sharing. Calling `formatUtcWithOffset` straight from a Server
 * Component (or during this Client Component's own SSR pass) would bake in
 * the SERVER CONTAINER's own timezone (always UTC in this stack) as if it
 * were the operator's local time. `formatUtc` alone is deterministic
 * everywhere and renders immediately; the real local offset is only knowable
 * once this runs in the operator's own browser, after mount.
 */
export function SystemAsOf({ iso }: SystemAsOfProps) {
  const [local, setLocal] = useState<string | null>(null);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- syncing from the runtime's own timezone, an external system, once mounted (H2)
    setLocal(formatLocalOffset(iso));
  }, [iso]);

  const utc = formatUtc(iso);
  return <span className="font-mono tabular-nums">{local ? `${utc} (${local})` : utc}</span>;
}
