import { Badge } from "@/components/ui/badge";
import { PortfolioAsOf } from "@/components/portfolio/portfolio-as-of";
import { unavailableLabel } from "@/components/portfolio/portfolio-format";
import type { PortfolioSummary } from "@/lib/api/portfolio-types";
import { formatBrl, formatUsdt } from "@/lib/format";

export interface PortfolioHeaderProps {
  summary: PortfolioSummary;
}

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border p-4">
      <p className="text-xs font-medium uppercase text-fg-muted">{label}</p>
      <p className="mt-1 font-mono text-2xl tabular-nums text-fg">{value}</p>
    </div>
  );
}

const NAO_DISPONIVEL = "não disponível";

/**
 * The wallet's header: equity side-by-side in USDT and BRL, cash, reserves,
 * `as_of`, and `marks_complete`/`unavailable` rendered as a visible warning
 * banner -- never folded into the numbers above as a silent zero (CLAUDE.md,
 * brief item 2). BRL equity is `summary.brl?.equity_brl`, never the USDT
 * figure multiplied by a rate this component would have to invent; when
 * `summary.brl` is `null` the BRL card names the reason instead of guessing.
 */
export function PortfolioHeader({ summary }: PortfolioHeaderProps) {
  const warnings: string[] = [];
  if (!summary.marks_complete) {
    warnings.push(
      "marcações a mercado incompletas -- os números abaixo usam a última marcação conhecida de cada posição, não o preço atual de todas",
    );
  }
  for (const code of summary.unavailable) {
    warnings.push(unavailableLabel(code));
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-semibold text-fg">{summary.name}</h2>
        <p className="text-xs text-fg-muted">
          Consultado em <PortfolioAsOf iso={summary.as_of} />
        </p>
      </div>

      {warnings.length > 0 && (
        <div className="rounded-md border border-warning/40 bg-bg-elevated p-3">
          <p className="text-xs font-semibold text-warning">Aviso</p>
          <ul className="mt-1 list-inside list-disc text-xs text-fg-muted">
            {warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <Kpi label="Patrimônio (USDT)" value={formatUsdt(summary.equity)} />
        <Kpi label="Patrimônio (BRL)" value={summary.brl ? formatBrl(summary.brl.equity_brl) : NAO_DISPONIVEL} />
        <Kpi label="Caixa" value={formatUsdt(summary.cash)} />
        <Kpi label="Reservado (caixa)" value={formatUsdt(summary.reserved_cash)} />
        <Kpi label="Reservado (risco)" value={formatUsdt(summary.reserved_risk)} />
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <Kpi label="Exposição" value={formatUsdt(summary.exposure_notional)} />
        <Kpi label="Reservado (notional)" value={formatUsdt(summary.reserved_notional)} />
        <Kpi label="Posições abertas" value={String(summary.open_position_count)} />
        <div className="rounded-md border border-border p-4">
          <p className="text-xs font-medium uppercase text-fg-muted">Tipo</p>
          <div className="mt-1 flex gap-1">
            <Badge variant="outline">{summary.type}</Badge>
            <Badge variant="outline">{summary.status}</Badge>
          </div>
        </div>
      </div>
    </div>
  );
}
