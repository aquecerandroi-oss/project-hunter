/**
 * Pure Placar logic (brief T3.18 item 3) -- sorting, verdict vocabulary, the
 * maturity bar's numbers, and the per-card display strings (money + research
 * units). No I/O, no JSX, so every branch is unit-testable without a DOM.
 * Split from `lab-money.ts` (generic row/scoreboard money math, reused here)
 * and from the presentational components, mirroring the split T3.17b already
 * made for the signals table (`buildTotalsDisplay`).
 */

import { reasonLabel, formatR, formatDecimalOrReason, signColorClass } from "@/components/lab/lab-format";
import { scoreboardMoney, type MoneyRuler } from "@/components/lab/lab-money";
import { formatBrlSigned, formatPct, formatUsdtSigned } from "@/lib/format";
import type { CurveOut, ScoreboardMaturityOut, ScoreboardRowOut } from "@/lib/api/lab-types";

// --- Verdict vocabulary (brief item 5: "sempre ao lado da régua que a produziu") ---

/** The API's field itself uses the masculine ("inconclusivo", matching Python's `Verdict` literal); the chip text agrees with "a versão" (Everton's own wording example uses "inconclusiva"). Falls back to the raw code for any value this frontend does not yet know, rather than disappearing. */
export const VERDICT_LABEL: Record<string, string> = {
  inconclusivo: "inconclusiva",
  validada: "validada",
  reprovada: "reprovada",
};

export function verdictLabel(verdict: string): string {
  return VERDICT_LABEL[verdict] ?? verdict;
}

export type VerdictBadgeVariant = "outline" | "positive" | "negative";

/** Chip: "inconclusiva muted, validada positive, reprovada negative" (brief item 3, literal). */
export const VERDICT_BADGE_VARIANT: Record<string, VerdictBadgeVariant> = {
  inconclusivo: "outline",
  validada: "positive",
  reprovada: "negative",
};

export function verdictBadgeVariant(verdict: string): VerdictBadgeVariant {
  return VERDICT_BADGE_VARIANT[verdict] ?? "outline";
}

/** Also the curve legend/line colour (brief item 4: "same colours as the cards"). */
export const VERDICT_LINE_COLOR_VAR: Record<string, string> = {
  inconclusivo: "--color-fg-muted",
  validada: "--color-green",
  reprovada: "--color-red",
};

export function verdictLineColorVar(verdict: string): string {
  return VERDICT_LINE_COLOR_VAR[verdict] ?? "--color-fg-muted";
}

/** SHADOW-LAB.md §10 / docs/plans/SHADOW-LAB.md "Placar (T3.18)" -- always shown next to the verdict, never left implicit (brief item 5). */
export const VERDICT_RULE_TEXT = "régua: 100 resultados e 30 dias; validada = expectancy > 0 e PF > 1";

// --- Ordering (brief item 3: "ordered active first then by sum_r") ---

function statusRank(status: string): number {
  return status === "active" ? 0 : 1;
}

function sumRValue(row: ScoreboardRowOut): number {
  return row.sum_r.value !== null ? Number(row.sum_r.value) : Number.NEGATIVE_INFINITY;
}

/** A version with no `sum_r` yet (no evaluable outcomes) sorts last within its status group, never ahead of a version with a real (even negative) number. */
export function sortScoreboardRows(rows: ScoreboardRowOut[]): ScoreboardRowOut[] {
  return [...rows].sort((a, b) => {
    const rankDiff = statusRank(a.version.status) - statusRank(b.version.status);
    if (rankDiff !== 0) return rankDiff;
    return sumRValue(b) - sumRValue(a);
  });
}

// --- Maturity bar (brief item 3: "37 de 100 resultados · 2 de 30 dias") ---

export function maturityBarText(maturity: ScoreboardMaturityOut): string {
  return `${maturity.evaluable} de ${maturity.threshold.outcomes} resultados · ${maturity.days} de ${maturity.threshold.days} dias`;
}

export interface MaturityRatios {
  outcomesPct: number;
  daysPct: number;
}

/** Capped at 100 -- the bar never overshoots once a threshold is cleared. */
export function maturityRatios(maturity: ScoreboardMaturityOut): MaturityRatios {
  const outcomesPct = maturity.threshold.outcomes > 0 ? Math.min(100, (maturity.evaluable / maturity.threshold.outcomes) * 100) : 100;
  const daysPct = maturity.threshold.days > 0 ? Math.min(100, (maturity.days / maturity.threshold.days) * 100) : 100;
  return { outcomesPct, daysPct };
}

// --- Card header text ---

export const SCOREBOARD_STATUS_LABEL: Record<string, string> = {
  active: "ativa",
  deprecated: "descontinuada",
  draft: "rascunho",
};

export function scoreboardStatusLabel(status: string): string {
  return SCOREBOARD_STATUS_LABEL[status] ?? status;
}

/** "desde 08/09/2026"; a version never activated (e.g. still `draft`) reads "ainda não ativada" rather than a blank or a fabricated date. UTC getters only -- same determinism rule as `lab-format.ts`'s `formatWhenShort`. */
export function formatSince(iso: string | null): string {
  if (iso === null) return "ainda não ativada";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "ainda não ativada";
  const day = String(date.getUTCDate()).padStart(2, "0");
  const month = String(date.getUTCMonth() + 1).padStart(2, "0");
  const year = date.getUTCFullYear();
  return `desde ${day}/${month}/${year}`;
}

// --- Empty-card reason (brief item 3: "empty card states say why -- no signals yet / all pending") ---

function pluralize(count: number, singular: string, plural: string): string {
  return count === 1 ? singular : plural;
}

/** Every emitted signal not yet resolved into a known `r_multiple`, beyond the three counts the API names (`pending`/`no_entry`/`censored`): still-open (`active`) outcomes and terminal outcomes the horizon gate has not matured yet. Named honestly instead of silently vanishing from the total. */
function remainderCount(row: ScoreboardRowOut): number {
  return Math.max(0, row.emitted - row.evaluable - row.pending - row.no_entry - row.censored);
}

/** `null` once the version has at least one evaluable outcome -- the card then shows real numbers instead of this sentence. */
export function noEvaluableReasonText(row: ScoreboardRowOut): string | null {
  if (row.evaluable > 0) return null;
  const parts: string[] = [];
  if (row.pending > 0) parts.push(`${row.pending} pendente${pluralize(row.pending, "", "s")}`);
  const remainder = remainderCount(row);
  if (remainder > 0) parts.push(`${remainder} em acompanhamento ou aguardando maturação`);
  if (row.no_entry > 0) parts.push(`${row.no_entry} sem entrada`);
  if (row.censored > 0) parts.push(`${row.censored} censurada${pluralize(row.censored, "", "s")}`);
  if (parts.length === 0) return `${row.emitted} sinais emitidos, nenhum ainda avaliável`;
  return `ainda sem resultado avaliável (${row.emitted} emitidos): ${parts.join(", ")}`;
}

// --- Card display assembly (kept out of JSX so the component's own cyclomatic complexity stays low, T3.17b lesson) ---

export interface ScoreboardCardDisplay {
  statusLabel: string;
  sinceText: string;
  noEvaluableReason: string | null;
  cumulativeUsdtText: string;
  cumulativeUsdtColor: string;
  cumulativeBrlText: string;
  avgUsdtText: string;
  avgUsdtColor: string;
  avgBrlText: string;
  hitRateText: string;
  hitRateIsValue: boolean;
  expectancyText: string;
  expectancyColor: string;
  pfText: string;
  pfIsValue: boolean;
  pfDetail: string;
  worstStreakText: string;
  maxDrawdownText: string;
}

function moneyText(money: { value: number | null; reason: string | null }, formatValue: (value: number) => string): string {
  return money.value !== null ? formatValue(money.value) : reasonLabel(money.reason ?? "sem motivo informado");
}

function moneyColor(value: number | null): string {
  if (value === null) return "text-fg-muted";
  return value > 0 ? "text-green" : value < 0 ? "text-red" : "text-fg";
}

export function buildScoreboardCardDisplay(row: ScoreboardRowOut, ruler: MoneyRuler): ScoreboardCardDisplay {
  const money = scoreboardMoney(row.sum_r, row.expectancy_r, ruler);
  const hitRate = row.hit_rate;
  const pf = row.profit_factor;
  const expectancy = formatR(row.expectancy_r.value, row.expectancy_r.reason ?? null);
  const pfFormatted = formatDecimalOrReason(pf.value, pf.reason ?? null);

  return {
    statusLabel: scoreboardStatusLabel(row.version.status),
    sinceText: formatSince(row.version.activated_at),
    noEvaluableReason: noEvaluableReasonText(row),
    cumulativeUsdtText: moneyText(money.cumulativeUsdt, formatUsdtSigned),
    cumulativeUsdtColor: moneyColor(money.cumulativeUsdt.value),
    cumulativeBrlText: moneyText(money.cumulativeBrl, formatBrlSigned),
    avgUsdtText: moneyText(money.avgPerOpUsdt, formatUsdtSigned),
    avgUsdtColor: moneyColor(money.avgPerOpUsdt.value),
    avgBrlText: moneyText(money.avgPerOpBrl, formatBrlSigned),
    hitRateText:
      hitRate.value !== null
        ? `${formatPct(hitRate.value, { signed: false })} (${hitRate.numerator}/${hitRate.denominator})`
        : reasonLabel(hitRate.reason ?? "sem motivo informado"),
    hitRateIsValue: hitRate.value !== null,
    expectancyText: expectancy.text,
    expectancyColor: expectancy.isValue ? signColorClass(row.expectancy_r.value) : "text-fg-muted",
    pfText: pfFormatted.text,
    pfIsValue: pfFormatted.isValue,
    pfDetail: `+${pf.sum_positive} / -${pf.sum_negative_abs} (n=${pf.sample_size})`,
    worstStreakText: row.worst_streak === 0 ? "sem sequência de perdas" : `${row.worst_streak} perda${pluralize(row.worst_streak, "", "s")} seguidas`,
    maxDrawdownText: `${row.max_drawdown_r}R`,
  };
}

// --- Curve series (brief item 4: one call per version, one line per version) ---

export interface LabCurveSeriesInput {
  versionId: string;
  label: string;
  verdict: string;
  points: CurveOut["points"];
  truncated: boolean;
  /** `true` when this version's own `/curve` fetch failed -- the line is simply absent, never a fabricated flat line. */
  failed: boolean;
}

/** Builds one series per scoreboard row from the per-version curve fetches (`Record<versionId, CurveOut | null>`, `null` meaning "fetch failed for this one"), in the same order as `rows` (callers pass the already-sorted list). */
export function buildCurveSeries(rows: ScoreboardRowOut[], curvesById: Record<string, CurveOut | null>): LabCurveSeriesInput[] {
  return rows.map((row) => {
    const curve = curvesById[row.version.id];
    const failed = curve === null || curve === undefined;
    return {
      versionId: row.version.id,
      label: `${row.version.strategy_key}/${row.version.version}`,
      verdict: row.verdict,
      points: curve?.points ?? [],
      truncated: curve?.truncated ?? false,
      failed,
    };
  });
}
