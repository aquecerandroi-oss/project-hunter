import { Badge } from "@/components/ui/badge";
import { formatPctOrUnavailable, killSwitchBadgeVariant, killSwitchLabel } from "@/components/portfolio/portfolio-format";
import type { KillSwitchDetail, PortfolioRiskState } from "@/lib/api/portfolio-types";
import { formatUsdt, formatUtc } from "@/lib/format";

export interface PortfolioRiskCardProps {
  riskState: PortfolioRiskState;
  killSwitch: KillSwitchDetail;
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-2 border-b border-border py-1.5 last:border-b-0">
      <span className="text-xs text-fg-muted">{label}</span>
      <span className="font-mono text-sm tabular-nums text-fg">{value}</span>
    </div>
  );
}

const DAILY_REFERENCE_NOTE = "a referência do dia (abertura em America/Sao_Paulo) não pôde ser reconstruída ainda";

/**
 * "Risco" (brief item 4): the São Paulo trading day, day-start equity, peak,
 * daily loss/drawdown percentages, and the effective kill switch with its
 * three unmerged scopes, reason and last transition -- evidence kept in a
 * `<details>` disclosure, not hidden away. `TRADING_DISABLED`/`EMERGENCY`
 * gets a red-bordered, visually distinct treatment per the brief ("kill
 * switch BLOQUEADO em destaque"). The `paper_v1` preset's numeric limits
 * (max risk per trade, exposure caps, participation) are NOT rendered here:
 * no endpoint exposes them yet (confirmed against
 * `packages/shared-types/src/generated/api.d.ts` -- only the `RiskPreset`
 * enum value travels over the wire, never the preset's numbers), and
 * CLAUDE.md forbids inventing them from `docs/RISK_ENGINE.md`'s prose.
 */
export function PortfolioRiskCard({ riskState, killSwitch }: PortfolioRiskCardProps) {
  const blocked = killSwitch.effective === "TRADING_DISABLED" || killSwitch.effective === "EMERGENCY";
  const dailyLoss = formatPctOrUnavailable(riskState.daily_loss_pct, DAILY_REFERENCE_NOTE);
  const drawdown = formatPctOrUnavailable(riskState.drawdown_pct, DAILY_REFERENCE_NOTE);

  return (
    <div className="rounded-md border border-border p-4">
      <h3 className="text-sm font-semibold text-fg">Risco</h3>

      <div className="mt-2">
        <Row label={`Dia (${riskState.trading_day_timezone})`} value={riskState.trading_day ?? "indisponível"} />
        <Row
          label="Patrimônio no início do dia"
          value={riskState.equity_day_start !== null ? formatUsdt(riskState.equity_day_start) : `indisponível (${DAILY_REFERENCE_NOTE})`}
        />
        <Row label="Pico de patrimônio" value={formatUsdt(riskState.peak_equity)} />
        <Row label="Pico observado em" value={formatUtc(riskState.peak_equity_observed_at)} />
        <Row label="Perda do dia" value={dailyLoss.text} />
        <Row label="Drawdown" value={drawdown.text} />
      </div>

      <div
        className={`mt-4 rounded-md border p-3 ${blocked ? "border-red bg-red-soft" : "border-border bg-bg-elevated"}`}
        data-testid="kill-switch-panel"
      >
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={killSwitchBadgeVariant(killSwitch.effective)}>{killSwitchLabel(killSwitch.effective)}</Badge>
          {killSwitch.blocks_entries && <span className="text-xs font-semibold text-red">Entradas bloqueadas</span>}
        </div>
        {killSwitch.reason && <p className="mt-2 text-sm text-fg">{killSwitch.reason}</p>}

        <div className="mt-2 grid grid-cols-3 gap-2 text-xs">
          <div>
            <p className="text-fg-muted">Sistema</p>
            <p className="font-mono text-fg">{killSwitch.scopes.system}</p>
          </div>
          <div>
            <p className="text-fg-muted">Organização</p>
            <p className="font-mono text-fg">{killSwitch.scopes.organization}</p>
          </div>
          <div>
            <p className="text-fg-muted">Carteira</p>
            <p className="font-mono text-fg">{killSwitch.scopes.portfolio}</p>
          </div>
        </div>

        {!killSwitch.daily_reference.available && (
          <p className="mt-2 text-xs text-warning">
            Referência do dia indisponível -- as entradas ficam bloqueadas mesmo que o interruptor em si esteja ATIVO, porque a perda diária
            não é mensurável sem ela.
          </p>
        )}

        {killSwitch.last_transition && (
          <details className="mt-3 text-xs text-fg-muted">
            <summary className="cursor-pointer text-fg">
              Última transição: {killSwitch.last_transition.from_state} → {killSwitch.last_transition.to_state} em{" "}
              {formatUtc(killSwitch.last_transition.created_at)}
            </summary>
            <div className="mt-2 space-y-1">
              <p>Ator: {killSwitch.last_transition.actor_type}{killSwitch.last_transition.actor_id ? ` (${killSwitch.last_transition.actor_id})` : ""}</p>
              {killSwitch.last_transition.reason && <p>Motivo: {killSwitch.last_transition.reason}</p>}
              <pre className="overflow-x-auto rounded-md border border-border bg-bg-overlay p-2 text-[11px]">
                {JSON.stringify(killSwitch.last_transition.evidence, null, 2)}
              </pre>
            </div>
          </details>
        )}
      </div>

      <p className="mt-3 text-[11px] text-fg-subtle">
        Limites do preset paper_v1 (risco por operação, exposição, participação): a API ainda não expõe os valores numéricos do preset nesta
        rota -- só os checks/decisões de propostas os publicariam (docs/plans/M3.md T3.12/T3.14), e este resumo não os inventa a partir da
        documentação.
      </p>
    </div>
  );
}
