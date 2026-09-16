/**
 * "Modo sozinho -- estágio 1" (T4.28/T4.28c) -- the block inside "Executor
 * real" that shows the stage-1 auto-approve the owner turned on 16/09/2026:
 * the executor opens the desk's `operator` proposal itself, inside the
 * written small-test scope, without the click. Rendered only when
 * `executor.auto_approve` is `true` (`LiveExecutorPanel`'s `LigadoBody`).
 * Server Component -- no hooks, the age lines are computed once against the
 * `nowMs` the page already resolved server-side (`@/lib/age`, never
 * `hooks/useAgeTicker.ts` -- that one is a client module and throws when a
 * Server Component calls it, T4.28d's 12:2x BRT incident).
 */
import { Badge } from "@/components/ui/badge";
import type { LiveExecutor } from "@/lib/api/meme-live-types";

import { AgeNote } from "./age-note";
import { autoApprovedLine, autoScopeLine } from "./live-format";
import { autoSkipLabel, executorRefusalLabel, gatesReloadErrorLabel, killSwitchLatchReasonLabel } from "./refusal-labels";

function sortedCounts(counts: Record<string, number>): [string, number][] {
  return Object.entries(counts).sort(([codeA, a], [codeB, b]) => b - a || codeA.localeCompare(codeB));
}

function ReasonChips({ title, counts, labelOf }: { title: string; counts: Record<string, number>; labelOf: (code: string) => string }) {
  const entries = sortedCounts(counts);
  if (entries.length === 0) return <p className="text-fg-muted">{title}: nenhuma nesta hora</p>;
  return (
    <div>
      <p className="text-fg-muted">{title}</p>
      <ul className="mt-1 flex flex-wrap gap-1.5">
        {entries.map(([code, count]) => (
          <li key={code} className="rounded-md bg-bg-overlay px-1.5 py-0.5 text-fg-muted">
            {labelOf(code)}: <span className="font-mono tabular-nums text-fg">{count}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ScopeLine({ executor }: { executor: LiveExecutor }) {
  const line = autoScopeLine(executor.gates, {
    usedSol: executor.small_test_used_sol ?? null,
    remainingSol: executor.small_test_remaining_sol ?? null,
    tradesDone: executor.small_test_trades_done ?? null,
    exhausted: executor.small_test_exhausted ?? null,
  });
  return (
    <div>
      <p className="text-fg-muted">Escopo do teste pequeno</p>
      <p className="font-mono tabular-nums text-fg">{line.tradesLine}</p>
      <p className="font-mono tabular-nums text-fg">{line.solLine}</p>
      {line.exhaustedLabel && <Badge variant="warning">{line.exhaustedLabel}</Badge>}
    </div>
  );
}

function GatesReloadLine({ executor, nowMs }: { executor: LiveExecutor; nowMs: number }) {
  const errorLabel = gatesReloadErrorLabel(executor.gates_reload_error);
  return (
    <div>
      <p className="text-fg-muted">Portões</p>
      <p className="text-fg">
        arquivo <AgeNote iso={executor.gates_mtime} nowMs={nowMs} prefix="mudou" /> ·{" "}
        <AgeNote iso={executor.gates_reloaded_at} nowMs={nowMs} prefix="recarregado" />
      </p>
      {errorLabel && <p className="text-warning">{errorLabel}</p>}
    </div>
  );
}

export function AutoStage1Block({ executor, nowMs }: { executor: LiveExecutor; nowMs: number }) {
  const on = executor.auto_approve === true;
  const latchLabel = killSwitchLatchReasonLabel(executor.kill_switch_latch_reason);
  return (
    <div className="rounded-md border border-border bg-bg-overlay p-3 text-xs">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <p className="text-sm font-semibold text-fg">Modo sozinho — estágio 1</p>
        <Badge variant={on ? "positive" : "default"}>{on ? "ligado" : "desligado"}</Badge>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <p className="font-mono tabular-nums text-fg">{autoApprovedLine(executor.auto_approved_1h ?? null, executor.auto_approve_max_per_hour ?? null)}</p>
        <ScopeLine executor={executor} />
        <ReasonChips title="Recusas da hora" counts={executor.auto_refused_1h} labelOf={(code) => executorRefusalLabel(code) ?? code} />
        <ReasonChips title="Pulos desta hora" counts={executor.auto_skipped} labelOf={autoSkipLabel} />
        <GatesReloadLine executor={executor} nowMs={nowMs} />
        {executor.kill_switch_latched && (
          <div>
            <p className="text-fg-muted">Corta-circuito</p>
            <p className="text-warning">travado{latchLabel ? ` — ${latchLabel}` : " (motivo: sem leitura)"}</p>
          </div>
        )}
      </div>
    </div>
  );
}
