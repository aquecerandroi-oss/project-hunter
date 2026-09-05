"use client";

import { useAuth } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { MarketRow } from "@/components/markets/market-row";
import { MarketsEmpty } from "@/components/markets/markets-empty";
import { MarketsTableHead, MARKETS_TABLE_HEADERS, type SortDirection, type SortKey } from "@/components/markets/markets-table-head";
import { SummaryChips } from "@/components/markets/summary-chips";
import { useArrowKeyRowSelection } from "@/hooks/useArrowKeyRowSelection";
import { useMarketChannels } from "@/hooks/useMarketChannels";
import { useRowHeight } from "@/hooks/useDensity";
import { useVirtualizedRows } from "@/hooks/useVirtualizedRows";
import type { MarketRow as MarketRowData, MarketsSummary, RtMarketMessage } from "@/lib/api/types";

export interface MarketsTableProps {
  orgSlug: string;
  items: MarketRowData[];
  summary: MarketsSummary;
  /** `MarketListPage.stale_after_ms` (H2) -- threaded down to every row's `QualityBadge`. */
  staleAfterMs: number;
  /** `true` when the API's `next_cursor` was non-null -- the monitored universe is bigger than this page, so search below only covers what was fetched (T1.5 review F6). */
  truncated?: boolean;
}

// Row height is `hooks/useDensity.ts`'s `useRowHeight()` (40px comfortable,
// 32px compact -- docs/DESIGN.md §2, joint decision #6), read once per
// render so the windowing math below and every row's own inline height stay
// the same number, never two constants that can drift apart. Manual
// windowing (no extra dependency was authorized for this task) is enough to
// satisfy CLAUDE.md's "tables virtualize at >= 200 rows" for the ~200-row
// monitored universe, and doubles as the "visible rows" set for realtime
// channel subscriptions (docs/plans/M1.md T1.5).
const OVERSCAN = 8;
const VIEWPORT_HEIGHT = 480;
// `MarketsTableHead`'s `<th>` cells are a fixed `h-8` (32px) regardless of
// density -- the sticky header occludes that much of the scroll container's
// top (T1.5b Astra must-fix #4).
const HEADER_HEIGHT = 32;

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

function rowId(row: MarketRowData): string {
  return `market-row-${row.exchange}-${row.symbol}`;
}

/** `/[orgSlug]/markets`'s table: search, sortable columns, virtualized rows, live prices for the visible window, keyboard-navigable rows. */
export function MarketsTable({ orgSlug, items, summary, staleAfterMs, truncated = false }: MarketsTableProps) {
  const { getToken } = useAuth();
  const router = useRouter();
  const rowHeight = useRowHeight();
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<{ key: SortKey; direction: SortDirection }>({ key: "quote_volume_24h", direction: "desc" });
  const [scrollTop, setScrollTop] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

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

  // Windowing math (M9: extracted out of this component -- also H1's home
  // for a density-driven, SSR-safe row height) lives in
  // `hooks/useVirtualizedRows.ts`.
  const { startIndex, endIndex, visibleRows, topPad, bottomPad } = useVirtualizedRows({
    rows: sorted,
    rowHeight,
    scrollTop,
    viewportHeight: VIEWPORT_HEIGHT,
    overscan: OVERSCAN,
  });

  const channels = useMemo(() => visibleRows.map((row) => `rt:market:${row.exchange}:${row.symbol}`), [visibleRows]);
  const { messages } = useMarketChannels({ channels, getAuthToken: () => getToken() });

  const { selectedIndex, handleKeyDown, reset: resetSelection } = useArrowKeyRowSelection({
    rowCount: sorted.length,
    rowHeight,
    viewportHeight: VIEWPORT_HEIGHT,
    stickyHeaderHeight: HEADER_HEIGHT,
    getScrollContainer: () => containerRef.current,
    onOpen: (index) => {
      // M3 (T1.5b fix pass 2, closing the PARTIAL from pass 1): membership in
      // the *rendered* window (`startIndex`/`endIndex`) is not the same
      // thing as being *visible* -- `useVirtualizedRows` renders `OVERSCAN`
      // (8) extra rows above and below the viewport so a fast scroll doesn't
      // flash empty rows, but those overscan rows sit off-screen. A manual
      // (mouse-wheel/scrollbar) scroll of as little as one row height can
      // leave `selectedIndex` pointing at a row that is still rendered (so
      // the old guard passed it) yet fully outside the viewport. The real
      // geometry is the same the sticky header forces `useArrowKeyRowSelection`
      // to use: a row's top edge in the scrollable content is
      // `HEADER_HEIGHT + index * rowHeight`, and it's only visible if that
      // span overlaps `[scrollTop, scrollTop + VIEWPORT_HEIGHT]` at all.
      const rowTop = HEADER_HEIGHT + index * rowHeight;
      const rowBottom = rowTop + rowHeight;
      const isVisible = rowBottom > scrollTop && rowTop < scrollTop + VIEWPORT_HEIGHT;
      if (!isVisible) {
        resetSelection();
        return;
      }
      const row = sorted[index];
      if (row) router.push(`/${orgSlug}/markets/${encodeURIComponent(row.exchange)}/${encodeURIComponent(row.symbol)}`);
    },
  });

  function handleSearchChange(value: string): void {
    setQ(value);
    setScrollTop(0);
    resetSelection();
    if (containerRef.current) containerRef.current.scrollTop = 0;
  }

  function toggleSort(key: SortKey): void {
    setSort((prev) => (prev.key === key ? { key, direction: prev.direction === "asc" ? "desc" : "asc" } : { key, direction: "desc" }));
  }

  useEffect(() => {
    // "/" focuses the search box from anywhere on the page (joint decision
    // #7) -- ignored while the user is already typing in an input/textarea.
    function handleGlobalSlash(event: KeyboardEvent): void {
      if (event.key !== "/") return;
      const target = event.target as HTMLElement | null;
      if (target && ["INPUT", "TEXTAREA"].includes(target.tagName)) return;
      event.preventDefault();
      searchRef.current?.focus();
    }
    window.addEventListener("keydown", handleGlobalSlash);
    return () => window.removeEventListener("keydown", handleGlobalSlash);
  }, []);

  if (items.length === 0) return <MarketsEmpty orgSlug={orgSlug} />;

  // `aria-activedescendant` must never reference an id that isn't actually
  // in the DOM right now -- manually scrolling (not via the arrow keys)
  // can carry the selected index outside the virtualized window's rendered
  // rows without moving `selectedIndex` itself (T1.5b Astra must-fix #4).
  const selectedRow = selectedIndex >= startIndex && selectedIndex < endIndex ? sorted[selectedIndex] : undefined;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <SummaryChips summary={summary} />
        <input
          ref={searchRef}
          type="search"
          value={q}
          onChange={(e) => handleSearchChange(e.target.value)}
          placeholder="Buscar símbolo... (/)"
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
        <div
          ref={containerRef}
          onScroll={(e) => setScrollTop(e.currentTarget.scrollTop)}
          onKeyDown={handleKeyDown}
          tabIndex={0}
          role="grid"
          aria-label="Mercados monitorados"
          aria-activedescendant={selectedRow ? rowId(selectedRow) : undefined}
          // M2 (T1.5b fix pass 2): the table is virtualized -- only a window
          // of `sorted.length` is ever rendered -- so without an explicit
          // `aria-rowcount` a screen reader has no way to know the grid has
          // more rows than the DOM currently holds; it would report the
          // window size as the total. `+ 1` accounts for the header row
          // (`aria-rowindex` 1 below), which also counts per the ARIA spec.
          aria-rowcount={sorted.length + 1}
          className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold"
          style={{ height: VIEWPORT_HEIGHT, overflowY: "auto" }}
        >
          {/*
           * `role="presentation"` on the `<table>` alone used to strip the
           * implicit `row`/`columnheader`/`cell` roles off every descendant
           * that had no role of its own (the WAI-ARIA conditionally-
           * presentational cascade) -- zero explicit roles were set anywhere
           * under `components/markets`, so the grid exposed no rows and no
           * cells at all: NVDA/JAWS announced "grid" with nothing inside it,
           * and `aria-activedescendant` pointed at a `<tr>` whose row
           * semantics had been stripped (M2, both reviewers, T1.5b fix pass
           * 2). The fix is a COMPLETE explicit role tree: `role="row"` on
           * every `<tr>` (`MarketsTableHead`'s header row included),
           * `role="columnheader"` on its `<th>`s, `role="gridcell"` on every
           * `MarketRow` `<td>` (see those two files). An element with its own
           * explicit role is excluded from the presentational cascade, so
           * `role="presentation"` here still only ever removes the table's
           * OWN redundant implicit `table`/`rowgroup` roles -- the div's
           * `grid` stays the only competing table-role-tree difference NVDA/
           * JAWS used to see, while the row/columnheader/gridcell tree
           * underneath it is now real and complete.
           */}
          <table role="presentation" className="w-full text-left text-[13px]">
            <MarketsTableHead sort={sort} onToggleSort={toggleSort} />
            <tbody>
              {topPad > 0 && (
                <tr aria-hidden="true" style={{ height: topPad }}>
                  <td colSpan={MARKETS_TABLE_HEADERS.length} />
                </tr>
              )}
              {visibleRows.map((row, visibleOffset) => {
                const absoluteIndex = startIndex + visibleOffset;
                return (
                  <MarketRow
                    key={`${row.exchange}:${row.symbol}`}
                    id={rowId(row)}
                    orgSlug={orgSlug}
                    row={applyLiveTick(row, messages[`rt:market:${row.exchange}:${row.symbol}`] as RtMarketMessage | undefined)}
                    staleAfterMs={staleAfterMs}
                    rowHeight={rowHeight}
                    selected={absoluteIndex === selectedIndex}
                    // Header row is `aria-rowindex` 1 (`MarketsTableHead`), so
                    // data row `absoluteIndex` (0-based) is `+ 2` (M2).
                    ariaRowIndex={absoluteIndex + 2}
                    onOpen={() => router.push(`/${orgSlug}/markets/${encodeURIComponent(row.exchange)}/${encodeURIComponent(row.symbol)}`)}
                  />
                );
              })}
              {bottomPad > 0 && (
                <tr aria-hidden="true" style={{ height: bottomPad }}>
                  <td colSpan={MARKETS_TABLE_HEADERS.length} />
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
      {sorted.length === 0 && q && (
        <p className="text-center text-sm text-fg-muted">Nenhum resultado para &quot;{q}&quot; nesta lista.</p>
      )}
    </div>
  );
}
