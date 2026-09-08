export interface LabHeaderDef {
  label: string;
  align?: "right";
  secondary?: boolean;
  /** A fixed minimum width so a short-but-important column (e.g. the "Resultado" badge) never gets squeezed off-screen when the table's natural width exceeds its container (brief T3.17b item 6). */
  minWidthClass?: string;
}

/**
 * Default view (brief T3.17, extended by T3.17b item 5): which strategy
 * emitted the signal, what it entered with, what it left with and why, how
 * long it stayed, profit or loss -- plain money, no "R". Always visible,
 * never behind the research toggle.
 */
export const LAB_MONEY_HEADERS: LabHeaderDef[] = [
  { label: "Estratégia" },
  { label: "Mercado" },
  { label: "Quando (Brasília)", minWidthClass: "min-w-[150px]" },
  { label: "Entrou", align: "right" },
  { label: "Saiu", align: "right" },
  { label: "Duração", align: "right" },
  { label: "Variação", align: "right" },
  { label: "Quantia simulada", align: "right" },
  { label: "Resultado", align: "right", minWidthClass: "min-w-[150px]" },
];

/** Research columns (brief T3.17b item 5's own list: "R líquido, R ex-funding, stop, alvo, tracking") -- only rendered behind the "Detalhes de pesquisa" toggle. `Versão`/`Referência`/`Toque` moved out: the strategy is now in "Estratégia" above, and the reference price/touch chip stay in the per-signal detail panel instead of repeating in every row. */
export const LAB_RESEARCH_HEADERS: LabHeaderDef[] = [
  { label: "R líquido", align: "right" },
  { label: "R ex-funding", align: "right", secondary: true },
  { label: "Stop", align: "right", secondary: true },
  { label: "Alvo", align: "right", secondary: true },
  { label: "Tracking" },
];

export function labSignalsHeaders(showResearch: boolean): LabHeaderDef[] {
  return showResearch ? [...LAB_MONEY_HEADERS, ...LAB_RESEARCH_HEADERS] : LAB_MONEY_HEADERS;
}

/** The `<thead>` of `LabSignalsTable` -- split out to keep that file under the lint config's 350-line budget, mirroring `components/markets/markets-table-head.tsx`. */
export function LabSignalsTableHead({ showResearch }: { showResearch: boolean }) {
  const headers = labSignalsHeaders(showResearch);
  return (
    <thead className="sticky top-0 bg-bg-overlay text-xs text-fg-muted">
      <tr role="row" aria-rowindex={1}>
        {headers.map((header) => (
          <th
            key={header.label}
            role="columnheader"
            className={`h-8 whitespace-nowrap px-3 font-medium ${header.align === "right" ? "text-right" : ""} ${
              header.secondary ? "hidden lg:table-cell" : ""
            } ${header.minWidthClass ?? ""}`}
          >
            {header.label}
          </th>
        ))}
      </tr>
    </thead>
  );
}
