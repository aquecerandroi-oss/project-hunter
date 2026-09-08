export interface LabHeaderDef {
  label: string;
  align?: "right";
  secondary?: boolean;
  /** A fixed minimum width so a short-but-important column (e.g. the "Resultado" badge) never gets squeezed off-screen when the table's natural width exceeds its container (brief T3.17b item 6). */
  minWidthClass?: string;
  /**
   * Below `md`, only the essential columns show (brief T3.24b item [3]:
   * "Estratégia, Mercado, Resultado") -- every other always-visible column
   * carries this flag, hidden until `md`.
   */
  mobileHidden?: boolean;
  /**
   * "Duração" and "Quantia simulada" live in the side panel too -- when a
   * row is selected on `lg` (panel open, narrowing the table), they hide
   * again until `xl` instead of fighting the panel for space (brief T3.24b
   * item [3]).
   */
  panelHidden?: boolean;
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
  { label: "Quando (Brasília)", minWidthClass: "min-w-[150px]", mobileHidden: true },
  { label: "Entrou", align: "right", mobileHidden: true },
  { label: "Saiu", align: "right", mobileHidden: true },
  { label: "Duração", align: "right", mobileHidden: true, panelHidden: true },
  { label: "Variação", align: "right", mobileHidden: true },
  { label: "Quantia simulada", align: "right", mobileHidden: true, panelHidden: true },
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

/** Same visibility class on the `<th>` and every row's matching `<td>` (`lab-signal-row.tsx`'s `labCellVisibilityClass`) -- a table column only stays aligned when header and body hide together. */
export function labCellVisibilityClass(header: Pick<LabHeaderDef, "secondary" | "mobileHidden" | "panelHidden">, panelOpen: boolean): string {
  if (header.secondary) return "hidden lg:table-cell";
  if (header.panelHidden) return panelOpen ? "hidden md:table-cell lg:hidden xl:table-cell" : "hidden md:table-cell";
  if (header.mobileHidden) return "hidden md:table-cell";
  return "";
}

/** The `<thead>` of `LabSignalsTable` -- split out to keep that file under the lint config's 350-line budget, mirroring `components/markets/markets-table-head.tsx`. */
export function LabSignalsTableHead({ showResearch, panelOpen }: { showResearch: boolean; panelOpen: boolean }) {
  const headers = labSignalsHeaders(showResearch);
  return (
    <thead className="sticky top-0 bg-bg-overlay text-xs text-fg-muted">
      <tr role="row" aria-rowindex={1}>
        {headers.map((header) => (
          <th
            key={header.label}
            role="columnheader"
            className={`h-8 whitespace-nowrap px-3 font-medium ${header.align === "right" ? "text-right" : ""} ${labCellVisibilityClass(header, panelOpen)} ${header.minWidthClass ?? ""}`}
          >
            {header.label}
          </th>
        ))}
      </tr>
    </thead>
  );
}
