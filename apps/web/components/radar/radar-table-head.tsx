import { cn } from "@/lib/utils";
import type { RadarSortKey, RadarSortOrder } from "@/lib/api/radar-types";

export interface RadarHeaderDef {
  key: RadarSortKey | null;
  label: string;
  align?: "right";
  secondary?: boolean;
}

// Server-side sort keys only (`RadarSortKey` -- `repositories/radar.py`):
// score, change, volume (via `relative_volume_1h`), age. Every other column
// (mercado, status, estágio, regime, qualidade, anomalias) has no sort key
// in the API contract, so its header is not a button.
export const RADAR_TABLE_HEADERS: RadarHeaderDef[] = [
  { key: null, label: "Mercado" },
  { key: "score", label: "Score", align: "right" },
  { key: null, label: "Status" },
  { key: null, label: "Estágio" },
  { key: null, label: "Regime" },
  { key: null, label: "Qualidade" },
  { key: null, label: "Anomalias", secondary: true },
  // `sort=age` orders by `first_seen_at` (`repositories/radar.py::_sort_raw_expr`),
  // not `last_updated_at` -- the header/cell/sort key must agree (Astra's
  // T2.7 diff review, must-fix 7).
  { key: "age", label: "Idade", align: "right", secondary: true },
];

export interface RadarTableHeadProps {
  sort: RadarSortKey;
  order: RadarSortOrder;
  onToggleSort: (key: RadarSortKey) => void;
}

/** The sortable `<thead>` of `radar-table.tsx` -- sorting here means a fresh server request, never a client-side re-order of the currently loaded page. */
export function RadarTableHead({ sort, order, onToggleSort }: RadarTableHeadProps) {
  return (
    <thead className="sticky top-0 bg-bg-overlay text-xs text-fg-muted">
      <tr role="row" aria-rowindex={1}>
        {RADAR_TABLE_HEADERS.map((header) => {
          const isSorted = header.key !== null && sort === header.key;
          const ariaSort: "ascending" | "descending" | "none" = isSorted ? (order === "asc" ? "ascending" : "descending") : "none";
          return (
            <th
              key={header.label}
              role="columnheader"
              className={cn("h-8 px-3 font-medium", header.align === "right" && "text-right", header.secondary && "hidden md:table-cell")}
              aria-sort={header.key ? ariaSort : undefined}
            >
              {header.key ? (
                <button type="button" onClick={() => onToggleSort(header.key as RadarSortKey)} className="hover:text-fg">
                  {header.label}
                  {isSorted ? (order === "asc" ? " ↑" : " ↓") : ""}
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
