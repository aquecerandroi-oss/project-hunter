/**
 * One token's four completion signals (T4.2d), each with its instant in
 * Brasília or "não visto", the pool's source, and the denominator's source --
 * amber when the signals disagree (some seen, some not), because that
 * disagreement is the finding, not noise to smooth over.
 */
import { BrasiliaInstant } from "@/components/time/brasilia-instant";
import type { MemeToken } from "@/lib/api/meme-types";

import { memeDenominatorSourceLabel, memePoolSourceLabel } from "./labels";
import { type CompletionSignal, completionSignals, signalsDisagree } from "./meme-graduation-signals";

function Signal({ signal }: { signal: CompletionSignal }) {
  return (
    <li className="flex flex-col gap-0.5 rounded-md border border-border p-3">
      <span className="text-[11px] font-medium uppercase tracking-wide text-fg-muted">{signal.label}</span>
      {signal.at ? (
        <>
          <BrasiliaInstant iso={signal.at} className="text-sm text-fg" />
          {signal.source && <span className="text-[11px] text-fg-subtle">fonte: {memePoolSourceLabel(signal.source)}</span>}
        </>
      ) : (
        <span className="text-sm text-fg-subtle">não visto</span>
      )}
    </li>
  );
}

export interface MemeSignalMarksProps {
  token: MemeToken;
}

export function MemeSignalMarks({ token }: MemeSignalMarksProps) {
  const signals = completionSignals(token);
  const disagree = signalsDisagree(signals);
  const seen = signals.filter((s) => s.at !== null).length;
  return (
    <section className="flex flex-col gap-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-medium text-fg">Sinais de conclusão</h2>
        {disagree ? (
          <p role="note" className="rounded-md border border-warning/40 bg-warning-soft px-2 py-1 text-[11px] font-medium text-warning">
            discordância: {seen} de 4 sinais vistos — o REST sozinho não prova graduação
          </p>
        ) : (
          <p className="text-[11px] text-fg-subtle">{seen === 0 ? "nenhum sinal visto" : "os quatro sinais concordam"}</p>
        )}
      </div>
      <ul className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {signals.map((signal) => (
          <Signal key={signal.key} signal={signal} />
        ))}
      </ul>
      <p className="text-[11px] text-fg-subtle">
        Conclusão pela regra: {token.completed_at ? <BrasiliaInstant iso={token.completed_at} /> : "ainda não"} · denominador do progresso:{" "}
        {memeDenominatorSourceLabel(token.progress_denominator_source)}
      </p>
    </section>
  );
}
