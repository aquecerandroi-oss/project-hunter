export interface LabHeaderDef {
  label: string;
  align?: "right";
  secondary?: boolean;
}

export const LAB_SIGNALS_HEADERS: LabHeaderDef[] = [
  { label: "Decisão (UTC)" },
  { label: "Mercado" },
  { label: "Versão", secondary: true },
  { label: "Referência", align: "right", secondary: true },
  { label: "Stop", align: "right", secondary: true },
  { label: "Alvo", align: "right", secondary: true },
  { label: "Entrada virtual", align: "right", secondary: true },
  { label: "Tracking" },
  { label: "Resultado" },
  { label: "R líquido", align: "right" },
  { label: "R ex-funding", align: "right", secondary: true },
];

/** The `<thead>` of `LabSignalsTable` -- split out to keep that file under the lint config's 350-line budget, mirroring `components/markets/markets-table-head.tsx`. */
export function LabSignalsTableHead() {
  return (
    <thead className="sticky top-0 bg-bg-overlay text-xs text-fg-muted">
      <tr role="row" aria-rowindex={1}>
        {LAB_SIGNALS_HEADERS.map((header) => (
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
