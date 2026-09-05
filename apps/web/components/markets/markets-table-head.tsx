import { cn } from "@/lib/utils";

export type SortKey = "symbol" | "last_price" | "price_change_24h_pct" | "quote_volume_24h" | "spread_pct";
export type SortDirection = "asc" | "desc";

export interface HeaderDef {
  key: SortKey | null;
  label: string;
  align?: "right";
  secondary?: boolean;
}

// Order keeps the mobile-essential columns (Mercado, Status/qualidade,
// Último, 24h %) contiguous; Bid/Ask/Spread/24h Vol are secondary detail
// hidden below `md` (joint decision #3, #9) via `MarketRow`'s `SECONDARY_CELL`.
export const MARKETS_TABLE_HEADERS: HeaderDef[] = [
  { key: "symbol", label: "Mercado" },
  { key: null, label: "Status" },
  { key: "last_price", label: "Último", align: "right" },
  { key: "price_change_24h_pct", label: "24h %", align: "right" },
  { key: null, label: "Bid", align: "right", secondary: true },
  { key: null, label: "Ask", align: "right", secondary: true },
  { key: "spread_pct", label: "Spread", align: "right", secondary: true },
  { key: "quote_volume_24h", label: "24h Vol", align: "right", secondary: true },
];

export interface MarketsTableHeadProps {
  sort: { key: SortKey; direction: SortDirection };
  onToggleSort: (key: SortKey) => void;
}

/** The sortable `<thead>` of `markets-table.tsx`, split out to keep that file under the lint config's per-function line/statement budget. */
export function MarketsTableHead({ sort, onToggleSort }: MarketsTableHeadProps) {
  return (
    <thead className="sticky top-0 bg-bg-overlay text-xs text-fg-muted">
      {/*
       * M2 (T1.5b fix pass 2): explicit `role="row"`/`aria-rowindex={1}` --
       * `markets-table.tsx`'s `role="presentation"` on the parent `<table>`
       * strips the *implicit* row role off an unmodified `<tr>`, and this is
       * the header row of a virtualized grid, so it must count itself as
       * row 1 of `aria-rowcount`, never rely on DOM position alone.
       */}
      <tr role="row" aria-rowindex={1}>
        {MARKETS_TABLE_HEADERS.map((header) => {
          const isSorted = header.key !== null && sort.key === header.key;
          const ariaSort: "ascending" | "descending" | "none" = isSorted
            ? sort.direction === "asc"
              ? "ascending"
              : "descending"
            : "none";
          return (
            <th
              key={header.label}
              role="columnheader"
              className={cn(
                "h-8 px-3 font-medium",
                header.align === "right" && "text-right",
                header.secondary && "hidden md:table-cell",
              )}
              aria-sort={header.key ? ariaSort : undefined}
            >
              {header.key ? (
                <button type="button" onClick={() => onToggleSort(header.key as SortKey)} className="hover:text-fg">
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
  );
}
