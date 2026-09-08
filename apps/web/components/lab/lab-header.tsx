import { LabAsOf } from "@/components/lab/lab-as-of";
import { commonAssumedCosts, formatAssumedCosts } from "@/components/lab/lab-costs";
import type { MoneyRuler } from "@/components/lab/lab-money";
import type { VersionSummaryOut } from "@/lib/api/lab-types";
import { formatUsdt } from "@/lib/format";

export interface LabHeaderProps {
  /** `null` when `loadLab` itself failed -- the banner still renders (brief T3.24b item [1]), just without a "consultado em" instant to show. */
  asOf: string | null;
  versions: VersionSummaryOut[];
  ruler: MoneyRuler;
}

/**
 * The fixed "SOMBRA" banner (brief S3b, compacted by T3.24b item [1] into
 * two lines): always visible, never a dismissible toast -- this is the one
 * label that must survive scroll, filters and empty/error states, since a
 * hypothetical number without it would read as real money. Moved above the
 * Placar (brief T3.24b §2, "opção A") and rendered even when the rest of
 * `/lab` failed to load, using the reference ruler in that case (`ruler` is
 * computed independently of `loadLab` in `lab/page.tsx`).
 *
 * Costs come from `coverage.assumed_costs`, never hardcoded (Astra's review:
 * they are per-version and may differ; see `lab-costs.ts`).
 */
export function LabHeader({ asOf, versions, ruler }: LabHeaderProps) {
  const common = commonAssumedCosts(versions);
  const costsText = common
    ? formatAssumedCosts(common)
    : versions.length > 0
      ? "discriminados por versão (ver cada card abaixo)"
      : "sem versão ativa para declarar";

  const rulerSource = ruler.isReference ? "carteira de referência, sem carteira aberta" : "carteira principal (paper)";

  return (
    <div data-testid="lab-header" className="rounded-md border border-border border-l-4 border-l-gold bg-bg-elevated px-4 py-3">
      <p data-testid="lab-money-banner" className="text-sm text-fg">
        SOMBRA — simulação sobre dado real. Nada foi comprado ou vendido.
      </p>
      <p data-testid="lab-money-ruler" className="mt-1 text-xs text-fg-muted">
        {`Régua: 0,25% de ${formatUsdt(ruler.equityUsdt)} (${rulerSource}) = ${formatUsdt(ruler.riskUsdt)} por operação · custos assumidos: ${costsText}`}
        {asOf !== null && (
          <>
            {" · consultado em "}
            <LabAsOf iso={asOf} />
          </>
        )}
      </p>
    </div>
  );
}
