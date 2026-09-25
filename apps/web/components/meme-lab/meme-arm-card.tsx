import { ruleSetKindLabel } from "@/components/meme-desk/labels";
import { formatSolSigned, formatR, signClass } from "@/components/meme-desk/meme-desk-format";
import type { MemeLabRuleSetBoard } from "@/lib/api/meme-lab-types";

import { ruleSetStatusLabel } from "./labels";
import { avgR, evaluableClosed, sumWindow } from "./meme-arms-format";

export interface MemeArmCardProps {
  ruleSet: MemeLabRuleSetBoard;
  /** The board's own window, in days -- printed once here so a zero-bet card still says over what period it is zero. */
  daysLimit: number;
}

function Stat({ label, value, hint, valueClass = "text-fg" }: { label: string; value: string; hint?: string | undefined; valueClass?: string }) {
  return (
    <div>
      <p className="text-[11px] uppercase tracking-wide text-fg-subtle">{label}</p>
      <p className={`font-mono text-sm font-semibold tabular-nums ${valueClass}`}>{value}</p>
      {hint && <p className="text-[11px] text-fg-subtle">{hint}</p>}
    </div>
  );
}

/**
 * One rule set's window results, past `evaluable` (Astra review 2026-09-25):
 * `closed` counts every closed bet, `indeterminate` among them has no
 * trustworthy `pnl_sol`/`r_multiple` (T4.16), so every average here divides
 * by `closed − indeterminate`, never by `closed` alone. `— · sem
 * fechamentos avaliáveis` outranks a fabricated 0 whenever that count is 0
 * but the rule set did bet in the window.
 */
function ResultStats({ ruleSet, daysLimit }: MemeArmCardProps) {
  const totals = sumWindow(ruleSet.days);
  const evaluable = evaluableClosed(totals);
  const r = avgR(totals.rSum, evaluable);
  const noEvaluableReason = totals.closed === 0 ? "todas abertas — sem fechamento ainda" : "sem fechamentos avaliáveis (todas indeterminadas)";
  return (
    <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
      <Stat label="Apostas" value={String(totals.entries)} hint={`${daysLimit} dias`} />
      <Stat label="Acertos" value={evaluable > 0 ? `${totals.wins} de ${evaluable}` : "—"} hint={evaluable > 0 ? "sobre as avaliáveis" : noEvaluableReason} />
      <Stat label="Resultado SOL" value={evaluable > 0 ? formatSolSigned(totals.netSol) : "—"} hint={evaluable > 0 ? undefined : noEvaluableReason} valueClass={evaluable > 0 ? signClass(totals.netSol) : "text-fg-muted"} />
      <Stat label="R médio" value={r === null ? "—" : formatR(String(r))} hint={evaluable > 0 ? "por aposta avaliável" : noEvaluableReason} valueClass={r === null ? "text-fg-muted" : signClass(String(r))} />
      {totals.indeterminate > 0 && <p className="col-span-2 text-[11px] text-warning sm:col-span-4">{totals.indeterminate} indeterminada(s) fora das somas acima (sem fotografia)</p>}
    </div>
  );
}

/**
 * One rule set's card (T4.91's `recuo_v1`, and every other paper arm alike --
 * data-driven off `GET /meme/lab`'s `rule_sets`, never a hardcoded roster):
 * what it is (name/version, kind, status, `exp_ref`), the one entry-timing
 * knob a pullback arm turns on (so it reads next to `operator/5`'s plain
 * card as "same gate, only entry timing differs" without this component
 * knowing either set's name), and the window's real numbers -- or an honest
 * "sem apostas na janela" when the set has not bet yet.
 */
export function MemeArmCard({ ruleSet, daysLimit }: MemeArmCardProps) {
  const hasBets = ruleSet.days.length > 0;
  return (
    <li className="rounded-md border border-border p-3 text-xs" data-testid="meme-arm-card">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="font-mono text-sm font-medium text-fg">
          {ruleSet.name}/{ruleSet.version}
        </span>
        <span className="flex flex-wrap items-center gap-1">
          <span className="rounded-md bg-bg-overlay px-1.5 py-0.5 text-[11px] text-fg-muted">{ruleSetKindLabel(ruleSet.kind)}</span>
          {ruleSet.status !== "active" && <span className="rounded-md bg-warning-soft px-1.5 py-0.5 text-[11px] font-medium text-warning">{ruleSetStatusLabel(ruleSet.status)}</span>}
        </span>
      </div>
      {ruleSet.exp_ref && <p className="mt-1 font-mono text-[11px] text-fg-subtle">{ruleSet.exp_ref}</p>}
      {ruleSet.entry_pullback && (
        <p className="mt-1 rounded-md border border-border-input bg-bg-overlay px-2 py-1 text-[11px] text-fg-muted">
          Única diferença de entrada: compra depois que o preço cai {ruleSet.entry_pullback.pct}% desde a máxima observada após a liberação do gate, em até {ruleSet.entry_pullback.window_s} s — o gate, a
          saída e o tamanho são os mesmos do conjunto do qual foi copiado.
        </p>
      )}
      {hasBets ? <ResultStats ruleSet={ruleSet} daysLimit={daysLimit} /> : <p className="mt-2 text-fg-muted">Sem apostas nos últimos {daysLimit} dias.</p>}
    </li>
  );
}
