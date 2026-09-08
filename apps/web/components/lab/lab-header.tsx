import { LabAsOf } from "@/components/lab/lab-as-of";
import { commonAssumedCosts, formatAssumedCosts } from "@/components/lab/lab-costs";
import type { MoneyRuler } from "@/components/lab/lab-money";
import type { VersionSummaryOut } from "@/lib/api/lab-types";
import { formatUsdt } from "@/lib/format";

export interface LabHeaderProps {
  asOf: string;
  versions: VersionSummaryOut[];
  ruler: MoneyRuler;
}

/**
 * The fixed "SOMBRA" banner (brief S3b): always visible, never a dismissible
 * toast -- this is the one label that must survive scroll, filters and
 * empty/error states, since a hypothetical number without it would read as
 * real money. Costs come from `coverage.assumed_costs`, never hardcoded
 * (Astra's review: they are per-version and may differ; see `lab-costs.ts`).
 */
export function LabHeader({ asOf, versions, ruler }: LabHeaderProps) {
  const common = commonAssumedCosts(versions);
  const costsText = common
    ? `custos assumidos: ${formatAssumedCosts(common)}`
    : versions.length > 0
      ? "custos assumidos: discriminados por versão (ver cada card abaixo)"
      : "custos assumidos: sem versão ativa para declarar";

  const rulerSource = ruler.isReference
    ? "carteira de referência, sem carteira aberta"
    : "carteira principal (paper)";
  const rulerText = `Régua: 0,25% de ${formatUsdt(ruler.equityUsdt)} (${rulerSource}) = ${formatUsdt(ruler.riskUsdt)} por operação`;

  return (
    // A thin gold left-border accent, not a tinted background -- docs/DESIGN.md
    // §2: "dourado é raro... nunca em fundos grandes". This banner is the
    // most important label on the page, but a large gold fill would still
    // read as decoration, not the emphasis rule allows (brand/one primary
    // action/active nav item/focus ring).
    <div data-testid="lab-header" className="rounded-md border border-border border-l-4 border-l-gold bg-bg-elevated px-4 py-3">
      <p className="text-sm font-semibold text-fg">
        SOMBRA — hipotético, sem capital{common ? `, ${costsText}` : ""}
      </p>
      {!common && <p className="text-xs text-fg-muted">{costsText}</p>}
      <p className="mt-1 text-xs text-fg-muted">
        Estado em <LabAsOf iso={asOf} />
      </p>
      <p data-testid="lab-money-banner" className="mt-2 text-sm text-fg">
        Simulação sobre dado real. Nada foi comprado ou vendido.
      </p>
      <p data-testid="lab-money-ruler" className="text-xs text-fg-muted">
        {rulerText} -- todo valor em dinheiro nesta tela é simulado: dado real, custos assumidos, sem dinheiro.
      </p>
    </div>
  );
}
