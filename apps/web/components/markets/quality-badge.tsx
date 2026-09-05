"use client";

import { Badge } from "@/components/ui/badge";
import { computeAgeMs, formatAge, useAgeTicker } from "@/hooks/useAgeTicker";
import type { MarketComponents, MarketDataQuality } from "@/lib/api/types";

export interface QualityBadgeProps {
  quality: MarketDataQuality;
  components: MarketComponents;
  /**
   * `stale_after_ms` straight off the API response (`MarketOut`/`MarketDetailOut`,
   * H2) -- the threshold the API itself used to compute `quality`. A hardcoded
   * client-side guess (this used to be a `STALE_AFTER_MS = 10_000` constant)
   * drifts the moment `MARKET_STALE_AFTER_S` is reconfigured: at 5s the API
   * already answers `stale` for a 7s-old component while a badge still
   * comparing against 10s cheerfully shows OK.
   */
  staleAfterMs: number;
  /** `has_open_gap` (H2) -- an open ingestion gap must still read as "gap" even when a required component is also currently absent. */
  hasOpenGap: boolean;
}

const REQUIRED = ["ticker", "book", "mark"] as const;

function requiredAges(components: MarketComponents, now: number): number[] {
  return REQUIRED.map((key) => computeAgeMs(components[key].ts, now)).filter(
    (age): age is number => age !== null,
  );
}

function hasAbsentRequired(components: MarketComponents): boolean {
  return REQUIRED.some((key) => components[key].quality === "absent");
}

/**
 * Per-row data-quality vocabulary (docs/plans/M1.md T1.5): `unavailable` a
 * neutral "sem dado", `degraded` a red "gap" (or "sem dado" when the real
 * cause is a currently-absent component, not an ingestion gap -- Astra's
 * T1.5 review). `ok`/`stale` are re-derived every tick from the required
 * components' own ages via `useAgeTicker`, not frozen at the value the
 * server returned at fetch time (docs/plans/M1.md's joint decision: a market
 * that goes quiet must visibly go stale without a new message, and a fresh
 * realtime tick must visibly bring it back).
 */
export function QualityBadge({ quality, components, staleAfterMs, hasOpenGap }: QualityBadgeProps) {
  const now = useAgeTicker();

  if (quality === "unavailable") {
    return <Badge variant="default">sem dado</Badge>;
  }

  if (quality === "degraded") {
    // An open gap is a real ingestion gap regardless of whether a component
    // also happens to be absent right now (H2) -- only fall back to "sem
    // dado" when the degradation has no open gap behind it.
    const label = hasOpenGap || !hasAbsentRequired(components) ? "gap" : "sem dado";
    return <Badge variant="negative">{label}</Badge>;
  }

  const ages = requiredAges(components, now);
  const maxAge = ages.length > 0 ? Math.max(...ages) : null;
  const isStale = maxAge !== null && maxAge > staleAfterMs;

  if (!isStale) {
    return (
      <Badge variant="positive" className="gap-1.5">
        <span className="size-1.5 rounded-full bg-green" aria-hidden="true" />
        OK
      </Badge>
    );
  }

  return <Badge variant="warning">{`atrasado ${formatAge(maxAge)}`}</Badge>;
}
