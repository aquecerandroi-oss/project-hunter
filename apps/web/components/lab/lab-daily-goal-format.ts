/**
 * Pure formatting/mapping for the "Meta diária" panel (brief T3.78, Everton
 * 2026-09-10 verbatim: goal is PROFIT, R$9.000/day minimum; show REAL profit
 * -- never a fake or projected number, `null` with its reason when the API
 * says so). No I/O here -- every function takes the already-parsed
 * `DailyGoalOut` (or one of its fields) and returns display-ready text, so
 * this module is unit-testable without a fetch or a DOM (mirrors
 * `components/lab/lab-format.ts`/`lab-money.ts`).
 */
import { reasonLabel, type DecimalOrReason } from "@/components/lab/lab-format";
import { fxSourceLabel } from "@/components/portfolio/labels";
import { compareDecimalStrings, formatBrl, formatUsdt } from "@/lib/format";
import { formatBrasiliaShort } from "@/lib/time";
import type { DailyGoalAxis, DailyGoalFx, DailyGoalOut, DailyGoalRateWithCounts } from "@/lib/api/lab-daily-goal-types";

// Reason codes specific to this endpoint (`.claude/state/notes-T3.78.md` §1)
// that `components/lab/lab-format.ts::REASON_LABELS` does not already know
// about -- `reasonLabel` falls back to these, then to its own generic
// "motivo: <code>" for anything neither map recognizes (never hides an
// unrecognized-but-real reason).
const DAILY_GOAL_REASON_LABELS: Record<string, string> = {
  summed_unavailable: "soma por aposta indisponível",
  incomplete_bet_pricing: "soma indisponível: falta tamanho para uma ou mais apostas avaliáveis",
  no_fx_observation: "sem cotação USDT/BRL registrada até o fim do dia",
  no_bets: "nenhuma aposta única precificável neste dia (nenhuma aposta)",
  no_priceable_bets: "nenhuma das apostas únicas do dia pôde ser precificada",
  no_portfolio: "sem carteira principal aberta",
  opening_anchor: "carteira aberta, ainda sem snapshot de patrimônio (usando o valor de abertura)",
};

/** Human label for a reason code from this endpoint, falling back to the shared Lab vocabulary and then to the generic "motivo: <code>" (never silently hidden). */
export function dailyGoalReasonLabel(reason: string): string {
  if (DAILY_GOAL_REASON_LABELS[reason]) return DAILY_GOAL_REASON_LABELS[reason];
  return reasonLabel(reason);
}

/** A BRL money field that is `null` exactly when it carries a reason (SHADOW-LAB.md §9's discipline, applied to this endpoint's own reason vocabulary). */
export function formatBrlOrReason(value: string | null, reason: string | null | undefined): DecimalOrReason {
  if (value !== null) return { text: formatBrl(value), isValue: true };
  return { text: reason ? dailyGoalReasonLabel(reason) : "sem motivo informado", isValue: false };
}

/** "2026-09-06" -> "06/09/2026". `day` is already a Brasília calendar day (the API's own default/`?day=` echo), never an instant -- no timezone conversion needed, only a display reshuffle. Returns "--" for anything that does not parse as `YYYY-MM-DD`. */
export function formatDailyGoalDay(day: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(day);
  if (!match) return "--";
  const [, year, month, dayOfMonth] = match;
  return `${dayOfMonth}/${month}/${year}`;
}

/** "3 apostas únicas · 5 linhas somadas (pooled)" -- the dedupe explanation the brief asks to always show next to the two counts (one line, plain language: pooled counts the same bet once per sibling version). */
export function betsCountsLine(uniqueBets: number, pooledBets: number): string {
  const extra = pooledBets - uniqueBets;
  const suffix =
    extra > 0
      ? ` -- ${extra} linha${extra === 1 ? "" : "s"} extra${extra === 1 ? "" : "s"} de versões-irmãs que decidiram a mesma barra`
      : "";
  return `${uniqueBets} aposta${uniqueBets === 1 ? "" : "s"} única${uniqueBets === 1 ? "" : "s"} · ${pooledBets} linha${pooledBets === 1 ? "" : "s"} somada${pooledBets === 1 ? "" : "s"} (pooled)${suffix}`;
}

/** "Pooled conta a mesma aposta uma vez por versão que a decidiu" -- the fixed, always-visible one-line explanation the brief requires. */
export const POOLED_EXPLANATION = "\"Pooled\" conta a mesma aposta uma vez por versão que a decidiu; \"única\" conta a barra decidida uma única vez, ganha por quem ativou primeiro.";

/** "eixo: r_net -- exclui 0 linha(s) e 0 aposta(s) única(s) com funding indefinido" -- the axis note, verbatim about what it names, required to render on this panel. */
export function axisNoteLine(axis: DailyGoalAxis): string {
  return `Eixo: ${axis.used} -- exclui, sem misturar, ${axis.pooled_funding_null} linha${axis.pooled_funding_null === 1 ? "" : "s"} pooled e ${axis.unique_funding_null} aposta${axis.unique_funding_null === 1 ? "" : "s"} única${axis.unique_funding_null === 1 ? "" : "s"} com funding indefinido (T3.75).`;
}

/** "1/1 (100%)" style hit-rate line, or its reason when `value` is `null` (never a silent 0%). */
export function hitRateLine(hitRate: DailyGoalRateWithCounts): DecimalOrReason {
  if (hitRate.value === null) {
    return { text: hitRate.reason ? dailyGoalReasonLabel(hitRate.reason) : "sem motivo informado", isValue: false };
  }
  const pct = Number(hitRate.value);
  const pctText = Number.isFinite(pct) ? `${(pct * 100).toFixed(0)}%` : hitRate.value;
  return { text: `${hitRate.numerator}/${hitRate.denominator} (${pctText})`, isValue: true };
}

export type GoalStatus = "met" | "below" | "unknown";

/**
 * Semantic status for the goal row (Everton 2026-09-10: "abaixo da meta =
 * neutro/atenção, nunca verde a não ser que >= meta com valores reais"):
 * green only when a REAL profit figure meets or beats the goal; `null` (no
 * real profit known) is neutral, never colored as if it were progress.
 */
export function goalStatus(progress: DailyGoalOut["progress"], goalBrl: string): GoalStatus {
  if (progress.real_brl_summed == null) return "unknown";
  return compareDecimalStrings(progress.real_brl_summed, goalBrl) >= 0 ? "met" : "below";
}

/** Tailwind class for `goalStatus` -- `text-warning` (below, real value known), `text-fg-muted` (unknown/no real value), `text-green` (met or beat, real value known). Never `text-red`: falling short of a stretch profit goal is not an error state (docs/DESIGN.md §2: color only with meaning). */
export function goalStatusClass(status: GoalStatus): string {
  if (status === "met") return "text-green";
  if (status === "below") return "text-warning";
  return "text-fg-muted";
}

/** Strips a leading "-" from a `Decimal` string -- `distance_to_goal_real_brl = goal_brl - progress.real_brl` (`services/lab_daily_goal.py::_progress`) can be negative once the day's real profit reaches or beats the goal; the panel reads sign from `goalStatus` and always prints the magnitude in words ("meta batida, sobrou X"), never a double negative like "sobrou −R$500". */
function magnitude(decimal: string): string {
  return decimal.startsWith("-") ? decimal.slice(1) : decimal;
}

/** "faltam R$X" (abaixo da meta), "meta batida, sobrou R$X" (>= meta), or the API's own reason when `distance_to_goal_real_brl` is `null` -- the single source of truth for the goal row's text, independently unit-testable from the color it renders in (`goalStatusClass`). */
export function distanceToGoalLine(progress: DailyGoalOut["progress"], goalBrl: string, valueOfOneRReason: string | null, fxReason: string | null): DecimalOrReason {
  if (progress.distance_to_goal_summed_brl == null || progress.real_brl_summed == null) {
    const reason = progress.summed_reason ?? valueOfOneRReason ?? fxReason ?? "summed_unavailable";
    return { text: reason ? dailyGoalReasonLabel(reason) : "sem motivo informado", isValue: false };
  }
  const status = goalStatus(progress, goalBrl);
  const amount = formatBrl(magnitude(progress.distance_to_goal_summed_brl));
  return { text: status === "met" ? `meta batida, sobrou ${amount}` : `faltam ${amount}`, isValue: true };
}

export interface DailyGoalRequiredLines {
  requiredOneR: DecimalOrReason;
  requiredUniqueR: DecimalOrReason;
}

/** "O que 1 R precisaria valer" / "quantos R únicos faltariam" -- both `null` (with the schema's own documented reason) rather than a division by zero. */
export function requiredLines(progress: DailyGoalOut["progress"]): DailyGoalRequiredLines {
  const requiredOneR: DecimalOrReason =
    progress.required_1r_brl !== null
      ? { text: formatBrl(progress.required_1r_brl), isValue: true }
      : { text: "sem apostas únicas hoje para dividir a meta", isValue: false };
  const requiredUniqueR: DecimalOrReason =
    progress.required_unique_r !== null
      ? { text: `${Number(progress.required_unique_r).toFixed(2)} R`, isValue: true }
      : { text: "1 R real de hoje é desconhecido -- não dá para dizer quantos faltariam", isValue: false };
  return { requiredOneR, requiredUniqueR };
}

/** A USDT money field that is `null` exactly when it carries a reason -- same contract as `formatBrlOrReason`, T3.78b (Everton, 2026-09-10: profit is real in USDT -- the traded currency -- first, independent of any FX rate). */
export function formatUsdtOrReason(value: string | null, reason: string | null | undefined): DecimalOrReason {
  if (value !== null) return { text: formatUsdt(value), isValue: true };
  return { text: reason ? dailyGoalReasonLabel(reason) : "sem motivo informado", isValue: false };
}

/** "5,00" -- `fx.rate` in the pt-BR decimal-comma convention, without a currency prefix (a rate is a ratio, not itself money): reuses `formatBrl`'s decimal-safe rounding/grouping and strips its leading "R$ ". */
function formatRatePlain(rate: string): string {
  return formatBrl(rate).replace(/^\D*/, "");
}

/** "14:32" from an ISO instant, Brasília time only (no date) -- `formatBrasiliaShort` already resolves the zone; this drops its "dd/mm " prefix for a line that already names the day elsewhere. */
function brasiliaTimeOnly(iso: string): string | null {
  const short = formatBrasiliaShort(iso);
  if (!short) return null;
  const time = short.split(" ")[1];
  return time ?? null;
}

/**
 * "cotação USDT/BRL 5,00 — Binance spot (ticker), 14:32 Brasília" -- the FX
 * observation behind every `real_brl_*` figure on this panel, rate + source
 * + instant visible together (Everton, 2026-09-10: "nunca um número sem a
 * fonte e o instante"), or the API's own reason when no observation was
 * available. Time renders in Brasília, plain-Portuguese, never the raw "BRT"
 * abbreviation (`lib/time.ts`'s own convention, brief T3.22 item 8).
 */
export function fxLine(fx: DailyGoalFx | null | undefined, fxReason: string | null | undefined): DecimalOrReason {
  if (!fx) {
    return { text: fxReason ? dailyGoalReasonLabel(fxReason) : "sem motivo informado", isValue: false };
  }
  const time = brasiliaTimeOnly(fx.observed_at);
  const when = time ? `, ${time} Brasília` : "";
  return {
    text: `cotação USDT/BRL ${formatRatePlain(fx.rate)} — ${fxSourceLabel(fx.source)}${when}`,
    isValue: true,
  };
}
