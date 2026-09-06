import { AnomalyStatusChip } from "@/components/anomalies/anomaly-status-chip";
import { EvaluationStateChip } from "@/components/anomalies/evaluation-state-chip";
import type { OpportunityDetailOut } from "@/lib/api/opportunities-types";
import type { RegimeOut } from "@/lib/api/regime-types";
import { formatUtc } from "@/lib/format";

/**
 * "Anomalias ativas ligadas" + regime, in one section (brief line 10). The
 * regime's `is_stale`/timestamp do not live on `OpportunityDetailOut` --
 * only `GET /api/v1/regime` carries them -- so `currentRegime` is the
 * matching row from that endpoint's current list (`detail.regime_id` ->
 * `RegimeOut.id`), fetched once by the detail page. `null` when there is no
 * match (a closed/superseded regime, or no `regime_id` at all): shown as its
 * own honest state, never silently treated as fresh.
 */
export function WhyContext({ detail, currentRegime }: { detail: OpportunityDetailOut; currentRegime: RegimeOut | null }) {
  return (
    <section className="grid gap-4 rounded-lg border border-border bg-bg-elevated p-4 md:grid-cols-2">
      <div>
        <h2 className="text-xs font-medium uppercase tracking-wide text-fg-muted">Anomalias ativas</h2>
        {detail.anomalies.length === 0 ? (
          <p className="mt-2 text-sm text-fg-muted">Nenhuma anomalia ativa ligada a este mercado.</p>
        ) : (
          <ul className="mt-2 flex flex-col gap-2">
            {detail.anomalies.map((a) => (
              <li key={a.id} className="flex flex-wrap items-center gap-2 text-sm">
                <span className="font-medium text-fg">{a.type}</span>
                <span className="font-mono text-xs tabular-nums text-fg-muted">severidade {a.severity}</span>
                <AnomalyStatusChip status={a.status} />
                <EvaluationStateChip state={a.evaluation_state} />
              </li>
            ))}
          </ul>
        )}
      </div>
      <div>
        <h2 className="text-xs font-medium uppercase tracking-wide text-fg-muted">Regime</h2>
        {!detail.regime_id ? (
          <p className="mt-2 text-sm text-fg-muted">Nenhum regime vinculado a este episódio.</p>
        ) : !currentRegime ? (
          <p className="mt-2 text-sm text-fg-muted">
            Regime {detail.regime ?? "—"} vinculado (id {detail.regime_id.slice(0, 8)}…), mas não confirmado na leitura atual de /regime -- pode ter sido
            substituído desde então.
          </p>
        ) : (
          <div className="mt-2 flex flex-col gap-1 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium text-fg">{currentRegime.regime}</span>
              <span className="text-xs text-fg-muted">escopo {currentRegime.scope}</span>
              {currentRegime.is_stale && <span className="text-xs text-warning">stale</span>}
            </div>
            <span className="text-xs text-fg-muted">desde {formatUtc(currentRegime.start_time)}</span>
            {currentRegime.regime === "UNKNOWN" && Object.keys(currentRegime.supporting_features).length > 0 && (
              <p className="text-xs text-fg-muted">
                Motivo: {JSON.stringify(currentRegime.supporting_features)}
              </p>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
