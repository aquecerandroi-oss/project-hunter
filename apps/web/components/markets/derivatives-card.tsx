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
}

function AgeSuffix({ ts }: { ts: string | null | undefined }) {
  const now = useAgeTicker();
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
export function DerivativesCard({ markPrice, openInterest, fundingRate, fundingKind, components }: DerivativesCardProps) {
  return (
    <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-3">
      <div>
        <dt className="text-xs uppercase tracking-wide text-fg-muted">Mark price</dt>
        <dd className="mt-1 font-mono tabular-nums text-fg">
          {formatPrice(markPrice)}
          <AgeSuffix ts={components.mark.ts} />
        </dd>
      </div>
      <div>
        <dt className="text-xs uppercase tracking-wide text-fg-muted">Open interest</dt>
        <dd className="mt-1 font-mono tabular-nums text-fg">
          {formatVolume(openInterest)}
          <AgeSuffix ts={components.open_interest.ts} />
        </dd>
      </div>
      <div>
        <dt className="text-xs uppercase tracking-wide text-fg-muted">Funding</dt>
        <dd className="mt-1 font-mono tabular-nums text-fg">
          {formatFundingRate(fundingRate)}
          {fundingKind && <span className="ml-1 text-fg-subtle">({fundingKind})</span>}
          <AgeSuffix ts={components.funding.ts} />
        </dd>
      </div>
    </dl>
  );
}
