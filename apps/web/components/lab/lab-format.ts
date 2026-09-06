/**
 * Shadow Lab-specific formatting (docs/DESIGN.md §1: tabular-nums, explicit
 * sign, semantic color; SHADOW-LAB.md §9: a `null` value always carries a
 * `reason`, which must render as readable text, never as `0` or a mute dash).
 */

// Known reason codes across `NullableMetric.reason`, `ProfitFactorOut.reason`,
// `SumOfROut.reason`, `r_multiple_reason`, `no_entry_reason`,
// `censored_reason` (contract-S3-lab.md, SHADOW-LAB.md §9). Anything not
// listed here still renders (with its raw code) rather than disappearing --
// an unrecognized reason is a real fact from the API, not something to hide.
const REASON_LABELS: Record<string, string> = {
  no_sample: "sem amostra madura nesta janela",
  no_losses: "sem perdas na amostra (todas as saídas foram positivas)",
  no_resolved_touches: "nenhum toque de alvo ou stop resolvido",
  not_applicable: "não aplicável",
  evaluation_state_not_persisted: "avaliação não é persistida (só o sinal emitido é durável)",
  late: "entrada perdida por atraso",
  geometry: "geometria inválida após revalidação (stop/entrada/alvo fora de ordem)",
  blocked: "mercado bloqueado (tracking hold de outra versão)",
  gap: "barra necessária irrecuperável (gap de dados)",
};

/** Human label for a reason code, splitting a `prefix:detail` shape (e.g. `gap:failed`, `late:delay`) so an unlisted detail still shows its known prefix. */
export function reasonLabel(reason: string): string {
  if (REASON_LABELS[reason]) return REASON_LABELS[reason];
  const prefix = reason.split(":")[0];
  if (prefix && REASON_LABELS[prefix]) return `${REASON_LABELS[prefix]} (${reason})`;
  return `motivo: ${reason}`;
}

export interface DecimalOrReason {
  text: string;
  isValue: boolean;
}

/** A Decimal-string metric that is `null` exactly when it carries a reason -- never a `0` or a dash standing in for "unknown" (SHADOW-LAB.md §9). */
export function formatDecimalOrReason(value: string | null, reason: string | null, suffix = ""): DecimalOrReason {
  if (value !== null) return { text: `${value}${suffix}`, isValue: true };
  return { text: reason ? reasonLabel(reason) : "sem motivo informado", isValue: false };
}

/** R-multiples keep the API's own sign (e.g. `-1.0421`) and get an explicit `R` unit. */
export function formatR(value: string | null, reason: string | null): DecimalOrReason {
  return formatDecimalOrReason(value, reason, "R");
}

/** Semantic color for a signed decimal string -- neutral (never colored) when the value is absent, matching `MarketRow`'s rule that missing data is never painted green. */
export function signColorClass(value: string | null): string {
  if (value === null) return "text-fg-muted";
  return value.trim().startsWith("-") ? "text-red" : "text-green";
}
