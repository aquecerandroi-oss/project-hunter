import { RegimeChip, StageChip, StatusChip } from "@/components/radar/status-chip";
import type { DecompositionResult, ExplanationResult } from "@/components/opportunities/decomposition-parse";
import type { OpportunityDetailOut } from "@/lib/api/opportunities-types";

const DIRECTION_LABEL: Record<string, string> = { long: "Long", short: "Short", neutral: "Sem direção" };

/**
 * The "why" panel's first section (brief line 10): direction, score,
 * confidence, status/stage/regime chips, and the deterministic pt-BR
 * `explanation.resumo` -- shown exactly as the API sent it, never
 * re-translated or re-summarized here.
 */
export function WhySummary({
  detail,
  decomposition,
  explanation,
}: {
  detail: OpportunityDetailOut;
  decomposition: DecompositionResult;
  explanation: ExplanationResult;
}) {
  return (
    <section className="rounded-lg border border-border bg-bg-elevated p-4">
      <div className="flex flex-wrap items-center gap-3">
        <span className="font-mono text-[28px] tabular-nums text-fg">{detail.score}</span>
        <span className="text-sm text-fg-muted">de 100</span>
        <span className="text-sm font-medium text-fg">{DIRECTION_LABEL[detail.direction] ?? detail.direction}</span>
        <StatusChip status={detail.status} />
        <StageChip stage={detail.stage} />
        <RegimeChip regime={detail.regime} />
      </div>
      <p className="mt-1 text-xs text-fg-muted">Confiança {detail.confidence}</p>
      {decomposition.recognized && !decomposition.eligible && (
        <p className="mt-2 text-sm text-warning">Sem evidência utilizável neste ciclo{decomposition.reason ? `: ${decomposition.reason}` : "."}</p>
      )}
      {explanation.recognized ? (
        <>
          <p className="mt-3 text-sm text-fg">{explanation.resumo}</p>
          {/*
           * `frases[0]` duplicates `resumo` (`explain()`'s own construction,
           * `explanation.py:246`) -- every sentence AFTER it (e.g.
           * `estagio_divergente`, `sem_evidencia`) is a real warning from the
           * scoring engine that must not be silently dropped just because it
           * has no dedicated section of its own (Astra's T2.7 diff review,
           * must-fix 6).
           */}
          {explanation.frases.length > 1 && (
            <ul className="mt-2 flex flex-col gap-1 text-xs text-fg-muted">
              {explanation.frases.slice(1).map((frase, index) => (
                <li key={`${frase.codigo}-${index}`}>{frase.texto}</li>
              ))}
            </ul>
          )}
        </>
      ) : (
        <p className="mt-3 text-sm text-fg-muted">Explicação em formato não reconhecido -- ver JSON bruto no rodapé técnico.</p>
      )}
    </section>
  );
}
