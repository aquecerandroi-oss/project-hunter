export interface OpportunitiesHeaderDef {
  label: string;
  align?: "right";
  secondary?: boolean;
}

// `/opportunities` has no server-side sort key of its own
// (`routers/opportunities.py::list_opportunities` always ranks by `score`
// desc, keyset-paginated) -- no sortable headers here, unlike `/radar`.
export const OPPORTUNITIES_TABLE_HEADERS: OpportunitiesHeaderDef[] = [
  { label: "Mercado" },
  { label: "Score", align: "right" },
  { label: "Status" },
  { label: "Estágio" },
  { label: "Regime" },
  { label: "Atualizado", align: "right", secondary: true },
];

export function OpportunitiesTableHead() {
  return (
    <thead className="sticky top-0 bg-bg-overlay text-xs text-fg-muted">
      <tr role="row" aria-rowindex={1}>
        {OPPORTUNITIES_TABLE_HEADERS.map((header) => (
          <th
            key={header.label}
            role="columnheader"
            className={`h-8 px-3 font-medium ${header.align === "right" ? "text-right" : ""} ${header.secondary ? "hidden md:table-cell" : ""}`}
          >
            {header.label}
          </th>
        ))}
      </tr>
    </thead>
  );
}
