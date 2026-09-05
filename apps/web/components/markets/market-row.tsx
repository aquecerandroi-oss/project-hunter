import Link from "next/link";
import type { CSSProperties } from "react";

import { QualityBadge } from "@/components/markets/quality-badge";
import { formatPrice, formatSignedPercentNumber, formatSpread, formatVolume } from "@/components/markets/format";
import type { MarketRow as MarketRowData } from "@/lib/api/types";
import { cn } from "@/lib/utils";

export interface MarketRowProps {
  orgSlug: string;
  row: MarketRowData;
  /** The API's own `stale_after_ms` (H2) -- `QualityBadge` ages this row's components against it, never a hardcoded client-side guess. */
  staleAfterMs: number;
  style?: CSSProperties;
}

/** One row of the markets table (docs/DESIGN.md §1: tabular-nums, right-aligned, explicit sign). */
export function MarketRow({ orgSlug, row, staleAfterMs, style }: MarketRowProps) {
  const changeNegative = row.price_change_24h_pct?.trim().startsWith("-") ?? false;
  return (
    <tr style={style} className="h-8 border-t border-border hover:bg-bg-overlay">
      <td className="px-3">
        <Link
          href={`/${orgSlug}/markets/${row.exchange}/${row.symbol}`}
          className="font-medium text-fg hover:text-gold"
        >
          {row.symbol}
        </Link>
        <span className="ml-1.5 text-[11px] text-fg-subtle">{row.exchange}</span>
      </td>
      <td className="px-3">
        <QualityBadge
          quality={row.data_quality}
          components={row.components}
          staleAfterMs={staleAfterMs}
          hasOpenGap={row.has_open_gap}
        />
      </td>
      <td className="px-3 text-right font-mono tabular-nums text-fg">{formatPrice(row.last_price)}</td>
      <td className="px-3 text-right font-mono tabular-nums text-fg-muted">{formatPrice(row.bid)}</td>
      <td className="px-3 text-right font-mono tabular-nums text-fg-muted">{formatPrice(row.ask)}</td>
      <td className="px-3 text-right font-mono tabular-nums text-fg-muted">{formatSpread(row.spread_pct)}</td>
      <td className={cn("px-3 text-right font-mono tabular-nums", changeNegative ? "text-red" : "text-green")}>
        {formatSignedPercentNumber(row.price_change_24h_pct)}
      </td>
      <td className="px-3 text-right font-mono tabular-nums text-fg-muted">{formatVolume(row.quote_volume_24h)}</td>
    </tr>
  );
}
