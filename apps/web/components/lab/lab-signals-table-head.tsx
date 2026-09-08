export interface LabHeaderDef {
  label: string;
  align?: "right";
  secondary?: boolean;
}

/**
 * Default view (brief T3.17): what a signal entered with, what it left with,
 * profit or loss -- plain money, no "R". Always visible, never behind the
 * research toggle.
 */
export const LAB_MONEY_HEADERS: LabHeaderDef[] = [
  { label: "Mercado" },
  { label: "Quando" },
  { label: "Entrou", align: "right" },
  { label: "Saiu", align: "right" },
  { label: "Variação", align: "right" },
  { label: "Quantia simulada", align: "right" },
  { label: "Resultado", align: "right" },
];

/** Research columns (R multiples, raw levels, tracking/touch state) -- only rendered behind the "Detalhes de pesquisa" toggle (brief T3.17 item 3/5: "'R' aparece só no toggle de pesquisa"). */
export const LAB_RESEARCH_HEADERS: LabHeaderDef[] = [
  { label: "Versão", secondary: true },
  { label: "Referência", align: "right", secondary: true },
  { label: "Stop", align: "right", secondary: true },
  { label: "Alvo", align: "right", secondary: true },
  { label: "Tracking" },
  { label: "Toque" },
  { label: "R líquido", align: "right" },
  { label: "R ex-funding", align: "right", secondary: true },
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
            className={`h-8 px-3 font-medium ${header.align === "right" ? "text-right" : ""} ${
              header.secondary ? "hidden lg:table-cell" : ""
            }`}
          >
            {header.label}
          </th>
        ))}
      </tr>
    </thead>
  );
}
