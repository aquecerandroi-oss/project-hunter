"use client";

import { formatFundingRate, formatPrice, formatVolume } from "@/components/markets/format";
import { computeAgeMs, formatAge, useAgeTicker } from "@/hooks/useAgeTicker";
import type { MarketComponents } from "@/lib/api/types";

export interface DerivativesCardProps {
  markPrice: string | null | undefined;
  openInterest: string | null | undefined;
  fundingRate: string | null | undefined;
  fundingKind: "estimated" | "realized" | null | undefined;
  components: MarketComponents;
  /** `MarketDetailOut.server_now` (T3.16) -- shares the market detail header's server-anchored clock; the fallback hint (when missing) is disclosed once on `QualityBadge`, not repeated here. */
  serverNow?: string | null | undefined;
}

const FUNDING_KIND_LABEL: Record<"estimated" | "realized", string> = {
  estimated: "estimado",
  realized: "realizado",
};

function AgeSuffix({ ts, serverNow }: { ts: string | null | undefined; serverNow: string | null | undefined }) {
  const { now } = useAgeTicker(serverNow);
  const ageMs = computeAgeMs(ts, now);
  if (ageMs === null) return <span className="text-fg-subtle"> · sem dado</span>;
  return <span className="text-fg-subtle"> · há {formatAge(ageMs)}</span>;
}

/**
 * Mark price, open interest and funding, each with its own age (docs/plans/M1.md
 * T1.5's staleness-per-component decision) -- the contract T1.4 exposes has
 * no index price or next-funding timestamp, so this never invents them
 * (CLAUDE.md's "no fake anything").
 */
export function DerivativesCard({ markPrice, openInterest, fundingRate, fundingKind, components, serverNow }: DerivativesCardProps) {
  return (
    <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-3">
      <div>
        <dt className="text-xs uppercase tracking-wide text-fg-muted">Mark price</dt>
        <dd className="mt-1 font-mono tabular-nums text-fg">
          {formatPrice(markPrice)}
          <AgeSuffix ts={components.mark.ts} serverNow={serverNow} />
        </dd>
      </div>
      <div>
        <dt className="text-xs uppercase tracking-wide text-fg-muted">Open interest</dt>
        <dd className="mt-1 font-mono tabular-nums text-fg">
          {formatVolume(openInterest)}
          <AgeSuffix ts={components.open_interest.ts} serverNow={serverNow} />
        </dd>
      </div>
      <div>
        <dt className="text-xs uppercase tracking-wide text-fg-muted">Funding</dt>
        <dd className="mt-1 font-mono tabular-nums text-fg">
          {formatFundingRate(fundingRate)}
          {fundingKind && <span className="ml-1 text-fg-subtle">({FUNDING_KIND_LABEL[fundingKind]})</span>}
          <AgeSuffix ts={components.funding.ts} serverNow={serverNow} />
        </dd>
      </div>
    </dl>
  );
}
