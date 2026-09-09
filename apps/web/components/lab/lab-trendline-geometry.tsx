import { formatPrice } from "@/components/markets/format";
import { eventKindLabel, lineKindLabel, type TrendlineGeometry } from "@/lib/lab-trendline";

export interface LabTrendlineGeometryProps {
  geometry: TrendlineGeometry;
  /** Portuguese labels of any field that failed to parse (brief: "no fabricated points" -- say what is missing rather than hide the whole panel). */
  missing: string[];
}

interface Field {
  label: string;
  value: string;
}

function numOrDash(value: number | null): string {
  return value !== null ? String(value) : "--";
}

function priceOrDash(value: number | null): string {
  return value !== null ? formatPrice(String(value)) : "--";
}

function channelValue(geometry: TrendlineGeometry): string {
  if (!geometry.channelAvailable) return "sem canal";
  return numOrDash(geometry.channelWidthAtr);
}

/** Every persisted geometry field, in Portuguese, in display order -- split out of the component purely to stay under the complexity lint budget (each field is one straight-line lookup, not a branch inside the component itself). */
function geometryFields(geometry: TrendlineGeometry): Field[] {
  return [
    { label: "Tipo", value: lineKindLabel(geometry.lineKind) },
    { label: "Evento", value: eventKindLabel(geometry.eventKind) },
    { label: "Identificador", value: geometry.lineId ?? "--" },
    { label: "Inclinação por barra", value: numOrDash(geometry.slopePerBar) },
    { label: "Toques", value: numOrDash(geometry.touches) },
    { label: "Violações", value: numOrDash(geometry.violations) },
    { label: "Primeiro índice", value: numOrDash(geometry.firstIdx) },
    { label: "Último índice", value: numOrDash(geometry.lastIdx) },
    { label: "Válida desde (índice)", value: numOrDash(geometry.validFromIdx) },
    { label: "Preço da linha na decisão", value: priceOrDash(geometry.priceAtDecision) },
    { label: "Distância do evento (ATR)", value: numOrDash(geometry.eventDistanceAtr) },
    { label: "Preço do pivô", value: priceOrDash(geometry.pivotLowPrice) },
    { label: "Índice do pivô", value: numOrDash(geometry.pivotLowIdx) },
    { label: "Barras do padrão", value: numOrDash(geometry.patternBars) },
    { label: "Pivôs no padrão", value: numOrDash(geometry.patternPivots) },
    { label: "Linhas vigentes na barra", value: numOrDash(geometry.patternLines) },
    { label: "Linhas aposentadas", value: numOrDash(geometry.patternRetiredLines) },
    { label: "Largura do canal (ATR)", value: channelValue(geometry) },
  ];
}

/**
 * "Geometria" panel (brief T3.49 item 2): every persisted field of the trend
 * line, in Portuguese, plus the full `pattern_params` record in a collapsed
 * `<details>` -- the same geometry the overlay chart drew, in a form Everton
 * can read and check field by field without opening the raw JSON.
 */
export function LabTrendlineGeometry({ geometry, missing }: LabTrendlineGeometryProps) {
  const manyLines = geometry.patternLines !== null && geometry.patternLines > 1;
  return (
    <div className="flex flex-col gap-2 rounded-md border border-border bg-bg-overlay p-3 text-xs">
      <p className="text-[11px] font-semibold uppercase text-fg-muted">Geometria da linha</p>
      <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {geometryFields(geometry).map((field) => (
          <div key={field.label}>
            <dt className="text-fg-muted">{field.label}</dt>
            <dd className="font-mono tabular-nums text-fg">{field.value}</dd>
          </div>
        ))}
      </dl>
      {manyLines && (
        <p className="text-fg-subtle">
          {geometry.patternLines} linhas estavam vigentes nesta barra; só a que decidiu tem geometria registrada (as demais não são desenhadas).
        </p>
      )}
      {missing.length > 0 && <p className="text-warning">Campos ausentes nesta decisão: {missing.join(", ")}.</p>}
      {geometry.patternParamsRaw !== null && (
        <details>
          <summary className="cursor-pointer text-fg-muted">Parâmetros do traçado (JSON)</summary>
          <pre className="mt-1 max-h-64 overflow-auto rounded border border-border bg-bg p-2 text-[11px] text-fg">
            {geometry.patternParams !== null ? JSON.stringify(geometry.patternParams, null, 2) : geometry.patternParamsRaw}
          </pre>
        </details>
      )}
    </div>
  );
}
