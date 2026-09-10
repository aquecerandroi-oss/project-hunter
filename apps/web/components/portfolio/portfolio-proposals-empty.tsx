import { PortfolioAsOf } from "@/components/portfolio/portfolio-as-of";

export interface PortfolioProposalsEmptyProps {
  asOf: string;
}

/**
 * "Ausência operacional" (docs/DESIGN.md §2, first case) since T3.72/T3.68
 * landed the write path (`POST .../orders`, `apps/api/hunter_api/services/
 * admission.py::file_manual_order`): the feature is real, this wallet simply
 * has not had a manual paper order filed yet. Superseded by
 * `ManualOrdersTable` the moment the list GET returns at least one row --
 * `portfolio/page.tsx` renders this only for the zero-rows case. Before
 * T3.72 this named "chega no M3" as "não construído ainda"; keep that wording
 * only if this component is ever needed again before the write path exists
 * on a given deployment.
 */
export function PortfolioProposalsEmpty({ asOf }: PortfolioProposalsEmptyProps) {
  return (
    <div className="rounded-md border border-dashed border-border bg-bg-elevated p-4">
      <h3 className="text-sm font-semibold text-fg">Propostas (ordens manuais)</h3>
      <p className="mt-1 text-sm text-fg-muted">
        Nenhuma ordem manual enviada ainda. Use "Nova ordem paper" para enviar a primeira -- o motor registra os checks e o limitante
        vencedor de cada decisão.
      </p>
      <p className="mt-2 text-xs text-fg-subtle">
        Consultado em <PortfolioAsOf iso={asOf} />.
      </p>
    </div>
  );
}
