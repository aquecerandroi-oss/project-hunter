"use client";

import { useAuth } from "@clerk/nextjs";
import { useMemo, useRef, useState } from "react";

import { MarketRow } from "@/components/markets/market-row";
import { MarketsEmpty } from "@/components/markets/markets-empty";
import { SummaryChips } from "@/components/markets/summary-chips";
import { useMarketChannels } from "@/hooks/useMarketChannels";
import type { MarketRow as MarketRowData, MarketsSummary, RtMarketMessage } from "@/lib/api/types";
import { cn } from "@/lib/utils";

export interface MarketsTableProps {
  orgSlug: string;
  items: MarketRowData[];
  summary: MarketsSummary;
  /** `MarketListPage.stale_after_ms` (H2) -- threaded down to every row's `QualityBadge`. */
  staleAfterMs: number;
  /** `true` when the API's `next_cursor` was non-null -- the monitored universe is bigger than this page, so search below only covers what was fetched (T1.5 review F6). */
  truncated?: boolean;
}

type SortKey = "symbol" | "last_price" | "price_change_24h_pct" | "quote_volume_24h" | "spread_pct";
type SortDirection = "asc" | "desc";

// Row height matches docs/DESIGN.md §2's table density (32px). Manual
// windowing (no extra dependency was authorized for this task) is enough to
// satisfy CLAUDE.md's "tables virtualize at >= 200 rows" for the ~200-row
// monitored universe, and doubles as the "visible rows" set for realtime
// channel subscriptions (docs/plans/M1.md T1.5).
const ROW_HEIGHT = 32;
const OVERSCAN = 8;
const VIEWPORT_HEIGHT = 480;

const HEADERS: { key: SortKey | null; label: string; align?: "right" }[] = [
  { key: "symbol", label: "Mercado" },
  { key: null, label: "Status" },
  { key: "last_price", label: "Último", align: "right" },
  { key: null, label: "Bid", align: "right" },
  { key: null, label: "Ask", align: "right" },
  { key: "spread_pct", label: "Spread", align: "right" },
  { key: "price_change_24h_pct", label: "24h %", align: "right" },
  { key: "quote_volume_24h", label: "24h Vol", align: "right" },
];

function toNumber(value: string | null | undefined): number {
  if (value === null || value === undefined) return Number.NaN;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : Number.NaN;
}

/**
 * NaN (missing data) always sorts last, regardless of direction. The sign is
 * applied *inside* the comparator, not via `.reverse()` on the ascending
 * result -- reversing would also flip the NaN-last rows to the front on a
 * descending sort, exactly the "nulls first" bug Astra's T1.5 review found.
 */
function sortRows(rows: MarketRowData[], key: SortKey, direction: SortDirection): MarketRowData[] {
  const sign = direction === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    if (key === "symbol") return sign * a.symbol.localeCompare(b.symbol);
    const left = toNumber(a[key]);
    const right = toNumber(b[key]);
    if (Number.isNaN(left) && Number.isNaN(right)) return 0;
    if (Number.isNaN(left)) return 1;
    if (Number.isNaN(right)) return -1;
    return sign * (left - right);
  });
}

/**
 * `candidate` only counts as fresher when it actually exists (H4: a worker
 * that hasn't shipped `price_ts`/`book_ts` yet must degrade honestly, never
 * fall back to the coalesced aggregate `ts`) and is not older than `current`.
 * `current` missing (component never had a timestamp) always counts the
 * candidate as fresher.
 */
function isFresher(current: string | null | undefined, candidate: string | null | undefined): candidate is string {
  if (!candidate) return false;
  if (!current) return true;
  const candidateTime = new Date(candidate).getTime();
  const currentTime = new Date(current).getTime();
  if (Number.isNaN(candidateTime) || Number.isNaN(currentTime)) return false;
  return candidateTime >= currentTime;
}

/**
 * H4: the price and the book age off DIFFERENT clocks -- `tick.price_ts`
 * (last trade/ticker price event) and `tick.book_ts` (last book event), never
 * `tick.ts` (the coalesced aggregate, bumped by either kind of event). Using
 * `ts` for both let a book-only update (trade feed stalled) republish the
 * same old price under a fresh-looking age, showing a stale price with a
 * green "OK" badge (Astra's T1.5-fixes-p1 review). Each half of the row only
 * ever advances against its own previous component timestamp, so an
 * out-of-order or duplicate message can't rewind a fresher value.
 */
function applyLiveTick(row: MarketRowData, tick: RtMarketMessage | undefined): MarketRowData {
  if (!tick) return row;
  let next = row;

  if (isFresher(row.components.ticker.ts, tick.price_ts)) {
    next = {
      ...next,
      // `?? null` at the end (not just `?? next.last_price`) collapses a
      // possible `undefined` from `next.last_price` (an optional field) into
      // an explicit `null` -- `exactOptionalPropertyTypes` rejects assigning
      // `undefined` itself to a `string | null` optional property.
      last_price: tick.price ?? next.last_price ?? null,
      bid: tick.bid ?? next.bid ?? null,
      ask: tick.ask ?? next.ask ?? null,
      components: { ...next.components, ticker: { ...next.components.ticker, ts: tick.price_ts, quality: "ok" } },
    };
  }

  if (isFresher(row.components.book.ts, tick.book_ts)) {
    next = {
      ...next,
      components: { ...next.components, book: { ...next.components.book, ts: tick.book_ts, quality: "ok" } },
    };
  }

  return next;
}

/** `/[orgSlug]/markets`'s table: search, sortable columns, virtualized rows, live prices for the visible window. */
export function MarketsTable({ orgSlug, items, summary, staleAfterMs, truncated = false }: MarketsTableProps) {
  const { getToken } = useAuth();
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<{ key: SortKey; direction: SortDirection }>({ key: "quote_volume_24h", direction: "desc" });
  const [scrollTop, setScrollTop] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return items;
    // `base_asset` is `string | null` (H1: the API `outerjoin`s onto `assets`,
    // so a market whose base-asset row isn't backfilled yet has it `null`) --
    // it simply never matches a search term rather than crashing on
    // `.toLowerCase()` of `null`.
    return items.filter(
      (row) => row.symbol.toLowerCase().includes(needle) || (row.base_asset?.toLowerCase().includes(needle) ?? false),
    );
  }, [items, q]);

  const sorted = useMemo(() => sortRows(filtered, sort.key, sort.direction), [filtered, sort]);

  // Clamped to `sorted.length`: filtering to a shorter list must not leave
  // `startIndex` pointing past its end from a scroll position set against
  // the *previous*, longer list -- that would slice out an empty window
  // and hide real matches (Astra's T1.5 review).
  const maxStartIndex = Math.max(0, sorted.length - 1);
  const startIndex = Math.min(maxStartIndex, Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN));
  const visibleCount = Math.ceil(VIEWPORT_HEIGHT / ROW_HEIGHT) + OVERSCAN * 2;
  const endIndex = Math.min(sorted.length, startIndex + visibleCount);
  const visibleRows = sorted.slice(startIndex, endIndex);
  const topPad = startIndex * ROW_HEIGHT;
  const bottomPad = (sorted.length - endIndex) * ROW_HEIGHT;

  const channels = useMemo(() => visibleRows.map((row) => `rt:market:${row.exchange}:${row.symbol}`), [visibleRows]);
  const { messages } = useMarketChannels({ channels, getAuthToken: () => getToken() });

  function handleSearchChange(value: string): void {
    setQ(value);
    setScrollTop(0);
    if (containerRef.current) containerRef.current.scrollTop = 0;
  }

  function toggleSort(key: SortKey): void {
    setSort((prev) => (prev.key === key ? { key, direction: prev.direction === "asc" ? "desc" : "asc" } : { key, direction: "desc" }));
  }

  if (items.length === 0) return <MarketsEmpty />;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <SummaryChips summary={summary} />
        <input
          type="search"
          value={q}
          onChange={(e) => handleSearchChange(e.target.value)}
          placeholder="Buscar símbolo..."
          aria-label="Buscar mercado"
          className="h-8 w-56 rounded-md border border-border bg-bg-overlay px-3 text-[13px] text-fg placeholder:text-fg-subtle"
        />
      </div>
      {truncated && (
        <p className="text-xs text-fg-muted">
          Mostrando os primeiros {items.length} mercados monitorados — a busca acima cobre apenas esta lista.
        </p>
      )}
      <div className="overflow-x-auto rounded-md border border-border">
        <div ref={containerRef} onScroll={(e) => setScrollTop(e.currentTarget.scrollTop)} style={{ height: VIEWPORT_HEIGHT, overflowY: "auto" }}>
          <table className="w-full text-left text-[13px]">
            <thead className="sticky top-0 bg-bg-overlay text-xs text-fg-muted">
              <tr>
                {HEADERS.map((header) => {
                  const isSorted = header.key !== null && sort.key === header.key;
                  const ariaSort: "ascending" | "descending" | "none" = isSorted
                    ? sort.direction === "asc"
                      ? "ascending"
                      : "descending"
                    : "none";
                  return (
                    <th
                      key={header.label}
                      className={cn("h-8 px-3 font-medium", header.align === "right" && "text-right")}
                      aria-sort={header.key ? ariaSort : undefined}
                    >
                      {header.key ? (
                        <button type="button" onClick={() => toggleSort(header.key as SortKey)} className="hover:text-fg">
                          {header.label}
                          {isSorted ? (sort.direction === "asc" ? " ↑" : " ↓") : ""}
                        </button>
                      ) : (
                        header.label
                      )}
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {topPad > 0 && (
                <tr aria-hidden="true" style={{ height: topPad }}>
                  <td colSpan={HEADERS.length} />
                </tr>
              )}
              {visibleRows.map((row) => (
                <MarketRow
                  key={`${row.exchange}:${row.symbol}`}
                  orgSlug={orgSlug}
                  row={applyLiveTick(row, messages[`rt:market:${row.exchange}:${row.symbol}`] as RtMarketMessage | undefined)}
                  staleAfterMs={staleAfterMs}
                />
              ))}
              {bottomPad > 0 && (
                <tr aria-hidden="true" style={{ height: bottomPad }}>
                  <td colSpan={HEADERS.length} />
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
      {sorted.length === 0 && q && <p className="text-center text-sm text-fg-muted">Nenhum mercado encontrado para &quot;{q}&quot;.</p>}
    </div>
  );
}
