/**
 * Shadow Lab-specific formatting (docs/DESIGN.md §1: tabular-nums, explicit
 * sign, semantic color; SHADOW-LAB.md §9: a `null` value always carries a
 * `reason`, which must render as readable text, never as `0` or a mute dash).
 */

import { formatBrasiliaShort } from "@/lib/time";
import type { OutcomeResult } from "@/lib/api/lab-types";

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
  no_entry: "sem entrada",
  no_stop: "sem stop registrado",
  zero_stop_distance: "stop igual à entrada (distância zero)",
  no_completed_operations: "nenhuma operação concluída nesta seleção",
  no_brl_wallet: "conversão em BRL indisponível (carteira sem decomposição BRL)",
  no_profit_operations: "nenhuma operação com lucro nesta página",
  no_loss_operations: "nenhuma operação com prejuízo nesta página",
  no_versions_in_selection: "nenhuma versão nesta seleção",
  not_aggregable_across_versions: "não agregável somando versões diferentes",
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

/**
 * Same `null` + reason contract as `formatDecimalOrReason`, but rounded to a
 * fixed number of decimals (brief T3.24b addendum A1: the Placar's "Replay"
 * block shows expectancy/PF at "2 casas" instead of the API's own, longer
 * Decimal string). Falls back to the raw string when it does not parse as a
 * finite number (never silently drops a real, if unexpected, value).
 */
export function formatRounded(value: string | null, reason: string | null, suffix = "", decimals = 2): DecimalOrReason {
  if (value === null) return { text: reason ? reasonLabel(reason) : "sem motivo informado", isValue: false };
  const num = Number(value);
  return { text: `${Number.isFinite(num) ? num.toFixed(decimals) : value}${suffix}`, isValue: true };
}

/** Semantic color for a signed decimal string -- neutral (never colored) when the value is absent, matching `MarketRow`'s rule that missing data is never painted green. */
export function signColorClass(value: string | null): string {
  if (value === null) return "text-fg-muted";
  return value.trim().startsWith("-") ? "text-red" : "text-green";
}

/**
 * "n=9, ordenada por exit_ts" -> "9 resultados, em ordem de saída" (brief
 * T3.24b item [4]): the sum-of-R metric's own `count`/`ordered_by` detail,
 * in plain language instead of the raw field names. `ordered_by` has only
 * ever been `"exit_ts"` in this contract (`SumOfROut`) -- an unrecognized
 * value still renders (with its own raw code) rather than disappearing.
 */
export function formatSumOfRDetail(count: number, orderedBy: string): string {
  const orderText = orderedBy === "exit_ts" ? "em ordem de saída" : `ordenada por ${orderedBy}`;
  return `${count} resultado${count === 1 ? "" : "s"}, ${orderText}`;
}

/** Same rule as `signColorClass`, for an already-numeric (not Decimal-string) percentage move -- kept as its own named function (rather than an inline ternary at every call site) so `LabSignalRow`'s own cyclomatic complexity stays under the lint config's budget. */
export function pctColorClass(pctMove: number | null): string {
  if (pctMove === null) return "text-fg-muted";
  return pctMove >= 0 ? "text-green" : "text-red";
}

/**
 * "Saiu"'s own "why it left" vocabulary (brief T3.17b item 5, Everton's own
 * wording): a verb-agreement phrasing ("saiu por: alvo/stop/expirou/
 * invalidada") distinct from `RESULT_LABEL` in `lab-signal-chips.tsx`, which
 * is an adjective describing "resultado" ("resultado: expirado/invalidado")
 * used by the chip and the detail panel. Both read correctly in their own
 * sentence; this one is never applied when `exit_price` is null (the row's
 * `tracking_state` branch -- "não entrou"/"censurada"/"aberta" -- covers
 * that case instead, see `saidaText`).
 */
export const EXIT_REASON_LABEL: Record<OutcomeResult, string> = {
  target: "alvo",
  stop: "stop",
  expired: "expirou",
  invalidated: "invalidada",
  open: "aberta",
};

/**
 * "08/09 02:05" -- day/month + hour:minute, always Brasília (brief T3.22,
 * 2026-09-08: every primary timestamp reads in the organization's own
 * timezone, never UTC and never the viewer's browser zone). A thin re-export
 * of `lib/time.ts`'s `formatBrasiliaShort` kept under this name so every
 * existing call site in the Lab (`WhenCell`, `lab-money.ts`'s
 * `priceAndTime`) stays unchanged. Previously UTC-only (brief T3.17b item 3:
 * "05:05:05 UTC (02:05:05 -03:00)" wrapped across four lines in the "Quando"
 * column; the fixed-width one-line replacement is unchanged, only the
 * timezone is). Returns `null` for an invalid timestamp so a caller can fall
 * back to "--".
 */
export function formatWhenShort(iso: string): string | null {
  return formatBrasiliaShort(iso);
}

/** Plain pt-BR-grouped integer (brief T3.37, D17's numeric convention decided 2026-09-08): `2135` -> `"2.135"` -- used by the segment tabs' real totals and the pager's "X–Y de Z" line, never a raw un-grouped number once it can run into the thousands. */
export function formatCount(value: number): string {
  return new Intl.NumberFormat("pt-BR").format(value);
}

export interface DurationResult {
  text: string;
  /** Why `text` is "--" -- never absent when it is (SHADOW-LAB.md §9's own rule extended to a derived, not-API-provided field). */
  reason: string | null;
}

/**
 * "Duração" column (brief T3.17b item 5): `exit_ts - entry_ts`, rendered
 * `h:mm`. Deliberately never computed against "now" for a still-open
 * position -- that would make a duration grow on every re-render of an
 * otherwise-static page without a real fetch, and disagree with whatever the
 * next `revalidate`/`AutoRefresh` cycle recomputes it as.
 */
export function durationText(entryTs: string | null, exitTs: string | null): DurationResult {
  if (entryTs === null) return { text: "--", reason: "sem entrada" };
  if (exitTs === null) return { text: "--", reason: "em aberto" };
  const entryMs = new Date(entryTs).getTime();
  const exitMs = new Date(exitTs).getTime();
  if (!Number.isFinite(entryMs) || !Number.isFinite(exitMs) || exitMs < entryMs) {
    return { text: "--", reason: "intervalo inválido" };
  }
  const totalMinutes = Math.round((exitMs - entryMs) / 60000);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return { text: `${hours}:${String(minutes).padStart(2, "0")}`, reason: null };
}
