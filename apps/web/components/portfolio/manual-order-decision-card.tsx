import { Badge } from "@/components/ui/badge";
import { checkStateLabel, limitCapLabel, riskCheckLabel } from "@/components/portfolio/manual-order-labels";
import type { RiskCheck, RiskDecision } from "@/lib/api/manual-orders-types";
import { formatPct, formatUsdt } from "@/lib/format";

export interface ManualOrderDecisionCardProps {
  decision: RiskDecision;
}

function CheckRow({ check }: { check: RiskCheck }) {
  const variant = check.state === "passed" ? "positive" : check.state === "failed" ? "negative" : "warning";
  return (
    <tr className="border-t border-border">
      <td className="py-1 pr-3">{riskCheckLabel(check.name)}</td>
      <td className="py-1 pr-3">
        <Badge variant={variant}>{checkStateLabel(check.state)}</Badge>
      </td>
      <td className="py-1 pr-3 font-mono tabular-nums text-fg-muted">{check.value ?? "--"}</td>
      <td className="py-1 pr-3 font-mono tabular-nums text-fg-muted">{check.limit ?? "--"}</td>
      <td className="py-1 pr-3 text-fg-muted">{check.message || "--"}</td>
    </tr>
  );
}

/**
 * Renders one `RiskDecision` (T3.72 item 1: "limitante vencedor, tamanho,
 * motivo de recusa"), vocabulary from `docs/RISK_ENGINE.md` via
 * `manual-order-labels.ts`. Approved and refused each get their own visible
 * treatment (green/red banner) -- never a single neutral "resultado" line
 * that hides which one happened, mirroring `PortfolioRiskCard`'s kill-switch
 * destaque.
 */
export function ManualOrderDecisionCard({ decision }: ManualOrderDecisionCardProps) {
  const rejectionReasons = decision.checks.filter((c) => c.state !== "passed");

  return (
    <div className={`rounded-md border p-3 ${decision.approved ? "border-green/40 bg-green-soft/40" : "border-red/40 bg-red-soft/40"}`}>
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={decision.approved ? "positive" : "negative"}>{decision.approved ? "Aprovada" : "Recusada"}</Badge>
        {decision.shadow_only && <span className="text-xs text-fg-muted">Sem β validado -- ficaria só em sombra</span>}
        {decision.cancel_pending && <span className="text-xs text-warning">Kill switch cancela entradas pendentes</span>}
      </div>

      {decision.approved && decision.sizing && (
        <div className="mt-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-3">
          <div>
            <p className="text-fg-muted">Tamanho aprovado</p>
            <p className="font-mono tabular-nums text-fg">{formatUsdt(decision.sizing.notional)}</p>
          </div>
          <div>
            <p className="text-fg-muted">Limitante vencedor</p>
            <p className="font-mono text-fg">{limitCapLabel(decision.sizing.binding_constraint)}</p>
          </div>
          <div>
            <p className="text-fg-muted">Distância do stop</p>
            <p className="font-mono tabular-nums text-fg">{formatPct(decision.sizing.stop_distance_pct)}</p>
          </div>
          <div>
            <p className="text-fg-muted">Risco planejado</p>
            <p className="font-mono tabular-nums text-fg">
              {formatUsdt(decision.sizing.planned_risk_quote)} ({formatPct(decision.sizing.planned_risk_pct)})
            </p>
          </div>
          <div>
            <p className="text-fg-muted">Preço do dimensionamento</p>
            <p className="font-mono tabular-nums text-fg">{formatUsdt(decision.sizing.sizing_price)}</p>
          </div>
          <div>
            <p className="text-fg-muted">Multiplicador do kill switch</p>
            <p className="font-mono tabular-nums text-fg">{decision.sizing.kill_switch_multiplier}×</p>
          </div>
        </div>
      )}

      {!decision.approved && rejectionReasons.length > 0 && (
        <p className="mt-2 text-sm text-fg">
          Motivo da recusa: {rejectionReasons.map((c) => riskCheckLabel(c.name)).join(", ")}.
        </p>
      )}

      <details className="mt-3 text-xs text-fg-muted">
        <summary className="cursor-pointer text-fg">Ver todos os checks ({decision.checks.length})</summary>
        <div className="mt-2 overflow-x-auto">
          <table className="w-full text-left text-[13px]">
            <thead>
              <tr className="text-xs text-fg-muted">
                <th className="py-1 pr-3">Check</th>
                <th className="py-1 pr-3">Estado</th>
                <th className="py-1 pr-3">Valor</th>
                <th className="py-1 pr-3">Limite</th>
                <th className="py-1 pr-3">Mensagem</th>
              </tr>
            </thead>
            <tbody>
              {decision.checks.map((check) => (
                <CheckRow key={check.name} check={check} />
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
