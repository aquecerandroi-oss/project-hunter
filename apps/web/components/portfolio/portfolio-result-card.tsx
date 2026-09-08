import { fxSourceLabel } from "@/components/portfolio/labels";
import { PortfolioAsOf } from "@/components/portfolio/portfolio-as-of";
import { brlUnavailableLabel, signColorClass } from "@/components/portfolio/portfolio-format";
import type { PortfolioAnchor, PortfolioSummary } from "@/lib/api/portfolio-types";
import { formatBrl, formatBrlSigned } from "@/lib/format";

export interface PortfolioResultCardProps {
  summary: PortfolioSummary;
  anchor: PortfolioAnchor;
}

function Row({ label, value, colorClass }: { label: string; value: string; colorClass?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-2 border-b border-border py-1.5 last:border-b-0">
      <span className="text-xs text-fg-muted">{label}</span>
      <span className={`font-mono text-sm tabular-nums ${colorClass ?? "text-fg"}`}>{value}</span>
    </div>
  );
}

/**
 * "Resultado" (brief item 3, diretiva do Everton §1: "mostrar resultados em
 * reais e na moeda operacional, separando resultado das operações de
 * variação cambial"). `hunter_core.portfolio.attribution.attribute_brl`'s
 * convention -- the operating result is attributed at the OPENING rate, the
 * currency term carries the rate's effect on the whole patrimony -- is named
 * on screen (`opening_rate`/`current_rate`, both sources) rather than hidden
 * behind the totals, exactly as that module's own docstring requires.
 */
export function PortfolioResultCard({ summary, anchor }: PortfolioResultCardProps) {
  const { brl, brl_unavailable_reason: reason, brl_unavailable_detail: detail } = summary;

  return (
    <div className="rounded-md border border-border p-4">
      <h3 className="text-sm font-semibold text-fg">Resultado (BRL)</h3>

      {!brl ? (
        <div className="mt-2 rounded-md border border-warning/40 bg-bg-elevated p-3">
          <p className="text-sm text-fg">BRL indisponível: {reason ? brlUnavailableLabel(reason) : "motivo não informado"}</p>
          {detail && <p className="mt-1 text-xs text-fg-muted">Detalhe técnico: {detail}</p>}
        </div>
      ) : (
        <div className="mt-2">
          <Row label="Abertura (capital creditado × câmbio de abertura)" value={formatBrl(brl.opening_brl)} />
          <Row label="Resultado operacional (câmbio de abertura)" value={formatBrlSigned(brl.operational_brl)} colorClass={signColorClass(brl.operational_brl)} />
          <Row label="Variação cambial" value={formatBrlSigned(brl.currency_brl)} colorClass={signColorClass(brl.currency_brl)} />
          <Row label="Resultado total" value={formatBrlSigned(brl.total_brl)} colorClass={signColorClass(brl.total_brl)} />
          <Row label="Patrimônio atual (BRL)" value={formatBrl(brl.equity_brl)} />

          <div className="mt-3 grid grid-cols-1 gap-2 text-xs text-fg-muted sm:grid-cols-2">
            <div>
              <p className="font-medium text-fg-muted">Câmbio de abertura</p>
              <p className="font-mono tabular-nums text-fg">{brl.opening_rate} BRL/USDT</p>
              <p>
                {fxSourceLabel(anchor.fx_observation.source)} · <PortfolioAsOf iso={anchor.fx_observation.observed_at} />
              </p>
              <p>
                R$ {anchor.origin_amount} → {anchor.credited_amount} USDT
              </p>
            </div>
            <div>
              <p className="font-medium text-fg-muted">Câmbio atual</p>
              <p className="font-mono tabular-nums text-fg">{brl.current_rate} BRL/USDT</p>
              <p>
                {fxSourceLabel(brl.fx_observation.source)} · <PortfolioAsOf iso={brl.fx_observation.observed_at} />
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
