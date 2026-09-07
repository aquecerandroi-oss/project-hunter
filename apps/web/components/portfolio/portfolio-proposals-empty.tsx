import { PortfolioAsOf } from "@/components/portfolio/portfolio-as-of";

export interface PortfolioProposalsEmptyProps {
  asOf: string;
}

/**
 * "Não construído ainda" (docs/DESIGN.md §2, second case): unlike the
 * positions/orders/trades tables below (which ARE implemented and simply
 * have no rows because no writer exists yet), a proposal with its checks and
 * winning limiter has no API at all today -- `apps/api/hunter_api/routers`
 * has no `proposals.py`. The real milestone that adds it is named
 * (`docs/plans/M3.md` T3.12/T3.14: the admission service and the shadow →
 * admission bridge), never claimed as an operational absence this screen
 * could otherwise explain.
 */
export function PortfolioProposalsEmpty({ asOf }: PortfolioProposalsEmptyProps) {
  return (
    <div className="rounded-md border border-dashed border-border bg-bg-elevated p-4">
      <h3 className="text-sm font-semibold text-fg">Propostas</h3>
      <p className="mt-1 text-sm text-fg-muted">
        Ainda sem propostas -- o serviço de admissão (com os checks e o limitante vencedor de cada decisão) chega em T3.12/T3.14, ainda não
        implementado.
      </p>
      <p className="mt-2 text-xs text-fg-subtle">
        Consultado em <PortfolioAsOf iso={asOf} />.
      </p>
    </div>
  );
}
