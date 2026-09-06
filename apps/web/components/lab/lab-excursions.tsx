import { Badge } from "@/components/ui/badge";

export interface LabExcursionsProps {
  /** `signal_outcomes.meta.excursions` verbatim (`SignalListItemOut.excursions`) -- unit is always `price`, never trimmed (contract-S3-lab.md). */
  excursions: Record<string, unknown>;
}

function asString(v: unknown): string | null {
  return typeof v === "string" ? v : null;
}

function asBoolean(v: unknown): boolean {
  return v === true;
}

function asBounds(v: unknown): [unknown, unknown] | null {
  return Array.isArray(v) && v.length === 2 ? [v[0], v[1]] : null;
}

/**
 * MFE/MAE honestly (SHADOW-LAB.md §5): `mfe`/`mae` are `null` exactly when
 * the OHLC data cannot reveal the true extreme -- shown as "indeterminado"
 * with the `bounds` range and an `ambiguous` badge, never a `0` standing in
 * for "unknown" (a real zero excursion is indistinguishable from a missing
 * one unless the reason is explicit).
 */
function ExcursionField({ label, value, bounds, unit }: { label: string; value: unknown; bounds: unknown; unit: string }) {
  const known = asString(value);
  if (known !== null) {
    return (
      <div>
        <dt className="text-fg-muted">{label}</dt>
        <dd className="font-mono tabular-nums text-fg">
          {known} {unit}
        </dd>
      </div>
    );
  }
  const range = asBounds(bounds);
  return (
    <div>
      <dt className="text-fg-muted">{label}</dt>
      <dd className="font-mono tabular-nums text-fg-muted">
        indeterminado{range ? ` (limites [${String(range[0])}, ${String(range[1])}] ${unit})` : ""}
      </dd>
    </div>
  );
}

export function LabExcursions({ excursions }: LabExcursionsProps) {
  const available = asBoolean(excursions.available);
  if (!available) {
    return <p className="text-xs text-fg-muted">excursões indisponíveis para este sinal</p>;
  }

  const unit = asString(excursions.unit) ?? "price";
  const bounds = (excursions.bounds ?? {}) as Record<string, unknown>;
  const ambiguous = asBoolean(excursions.ambiguous);
  const coverage = (excursions.coverage ?? {}) as Record<string, unknown>;

  return (
    <div className="flex flex-col gap-1 text-xs">
      <dl className="grid grid-cols-2 gap-2">
        <ExcursionField label="MFE (favorável)" value={excursions.mfe} bounds={bounds.mfe} unit={unit} />
        <ExcursionField label="MAE (adverso)" value={excursions.mae} bounds={bounds.mae} unit={unit} />
      </dl>
      <div className="flex flex-wrap items-center gap-1.5">
        {ambiguous && <Badge variant="warning">ambíguo</Badge>}
        {"bars_known" in coverage && "bars_total" in coverage && (
          <span className="text-fg-subtle">
            {`cobertura de barras: ${String(coverage.bars_known)}/${String(coverage.bars_total)}`}
          </span>
        )}
      </div>
    </div>
  );
}
