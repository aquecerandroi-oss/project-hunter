"use client";

import Link from "next/link";

import { QualityBadge } from "@/components/markets/quality-badge";
import { formatPrice, formatSignedPercentNumber, formatSpread, formatVolumeWithUnit } from "@/components/markets/format";
import { usePriceFlash } from "@/hooks/usePriceFlash";
import type { MarketRow as MarketRowData } from "@/lib/api/types";
import { cn } from "@/lib/utils";

export interface MarketRowProps {
  id: string;
  orgSlug: string;
  row: MarketRowData;
  /** The API's own `stale_after_ms` (H2) -- `QualityBadge` ages this row's components against it, never a hardcoded client-side guess. */
  staleAfterMs: number;
  /** `hooks/useDensity.ts`'s row height -- the single source both the virtualization math and this row's own height read, so they cannot drift apart (joint decision #6). */
  rowHeight: number;
  /** True when `MarketsTable`'s keyboard navigation (arrow keys) currently points at this row -- gold, one of the few permitted uses (docs/DESIGN.md §2: "foco"). */
  selected?: boolean;
  /** 1-based ARIA row index within the full (unvirtualized) row count -- `MarketsTable`'s `absoluteIndex + 2` (header row is 1). M2, T1.5b fix pass 2: without this, a screen reader announces the rendered window's position, not this row's real position in the whole monitored universe. */
  ariaRowIndex: number;
  /** Opens the market detail when the row body is clicked (the symbol link keeps its own navigation). */
  onOpen?: () => void;
}

// Bid/Ask/Spread/Volume are secondary detail (joint decision #3: "menos
// dourado/chips", #9: "colunas essenciais no mobile" -- símbolo, preço,
// variação, qualidade). Hidden below `md`, always available on desktop.
const SECONDARY_CELL = "hidden px-3 text-right font-mono tabular-nums text-fg-muted md:table-cell";

/** One row of the markets table (docs/DESIGN.md §1: tabular-nums, right-aligned, explicit sign). */
export function MarketRow({ id, orgSlug, row, staleAfterMs, rowHeight, selected = false, ariaRowIndex, onOpen }: MarketRowProps) {
  // M4 (T1.5b fix pass): a `null`/absent `price_change_24h_pct` used to
  // default `changeNegative` to `false`, which colored the honest "--"
  // placeholder GREEN -- asserting "positive" over data that doesn't exist,
  // violating CLAUDE.md's no-invented-signal rule. Green/red only apply to a
  // real value; absent data is neutral.
  const hasChange = row.price_change_24h_pct !== null && row.price_change_24h_pct !== undefined;
  const changeNegative = row.price_change_24h_pct?.trim().startsWith("-") ?? false;
  const flash = usePriceFlash(row.last_price);

  return (
    <tr
      id={id}
      role="row"
      aria-rowindex={ariaRowIndex}
      aria-selected={selected}
      style={{ height: rowHeight }}
      className={cn("cursor-pointer border-t border-border hover:bg-bg-overlay", selected && "bg-bg-overlay ring-1 ring-inset ring-gold")}
      onClick={(event) => {
        // The symbol <Link> navigates by itself; every other cell opens the detail too.
        if ((event.target as HTMLElement).closest("a, button")) return;
        onOpen?.();
      }}
    >
      <td role="gridcell" className="px-3">
        <Link
          href={`/${orgSlug}/markets/${encodeURIComponent(row.exchange)}/${encodeURIComponent(row.symbol)}`}
          className="font-medium text-fg hover:text-gold"
        >
          {row.symbol}
        </Link>
        {/* 11px: named exception to the 5-size scale (docs/DESIGN.md §2) -- the exchange code is secondary metadata next to the symbol, same tier as `fg-subtle` labels/ages. */}
        <span className="ml-1.5 text-[11px] text-fg-subtle">{row.exchange}</span>
      </td>
      <td role="gridcell" className="px-3">
        <QualityBadge
          quality={row.data_quality}
          components={row.components}
          staleAfterMs={staleAfterMs}
          hasOpenGap={row.has_open_gap}
        />
      </td>
      <td
        role="gridcell"
        className={cn(
          "px-3 text-right font-mono tabular-nums text-fg",
          flash === "up" && "flash-up",
          flash === "down" && "flash-down",
        )}
      >
        {formatPrice(row.last_price)}
      </td>
      <td
        role="gridcell"
        className={cn(
          "px-3 text-right font-mono tabular-nums",
          !hasChange ? "text-fg-muted" : changeNegative ? "text-red" : "text-green",
        )}
      >
        {formatSignedPercentNumber(row.price_change_24h_pct)}
      </td>
      <td role="gridcell" className={SECONDARY_CELL}>{formatPrice(row.bid)}</td>
      <td role="gridcell" className={SECONDARY_CELL}>{formatPrice(row.ask)}</td>
      <td role="gridcell" className={SECONDARY_CELL}>{formatSpread(row.spread_pct)}</td>
      <td role="gridcell" className={SECONDARY_CELL}>{formatVolumeWithUnit(row.quote_volume_24h, row.quote_asset)}</td>
    </tr>
  );
}
