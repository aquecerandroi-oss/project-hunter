/**
 * The Lab in plain money terms (brief T3.17, Everton 2026-09-08 verbatim:
 * "o front do lab deixa mais facil de saber -- quero que ele mostre oque
 * investiu ou simulou a quantia se saiu ou nao no lucro"). The Shadow Lab
 * never traded (SHADOW-LAB.md): every number here is hypothetical, derived
 * from ONE declared, visible rule instead of a persisted ledger --
 * `risk_per_trade_pct` (the paper_v1 preset, `docs/RISK_ENGINE.md` §3, "0,25%
 * é o teto declarado") applied to the organization's real principal paper
 * wallet equity (`GET /portfolios` + its summary), or a fixed, labelled
 * reference when no wallet is open yet. Every function is pure (no I/O) so
 * the money math is unit-testable without a fetch or a DOM.
 *
 * Money math here deliberately uses `Number`, not the string/BigInt path
 * `lib/format.ts` uses for *rendering* a single Decimal string. These
 * computations do real arithmetic (multiplication, division) across two or
 * three already-hypothetical inputs, purely for on-screen translation --
 * never persisted, never sent back to the API, never a substitute for a real
 * ledger (CLAUDE.md's "Decimal, never float" rule targets stored money; nothing
 * here is stored). The inputs are ordinary financial magnitudes (well under
 * 2^53), so IEEE-754 double precision cannot lose a digit that would change
 * the rounded-to-2-decimals result `formatUsdt`/`formatBrl` render downstream.
 */

import { EXIT_REASON_LABEL, formatWhenShort, reasonLabel } from "@/components/lab/lab-format";
import { formatPrice } from "@/components/markets/format";
import type { OutcomeResult, SignalListItemOut, VersionSummaryOut } from "@/lib/api/lab-types";

/** paper_v1's own risk ceiling (`docs/RISK_ENGINE.md` §3) -- a declared product rule, not a per-organization API field, so it is a named constant here rather than fetched per request (mirrors `LAB_LABEL` being a fixed string on the API side, `hunter_api/schemas/lab_common.py`). */
export const RISK_PER_TRADE_PCT = 0.0025;

/** The fixed suffix/tooltip every money figure on this screen carries (brief T3.17): never hidden, so a simulated number never reads as real money. */
export const MONEY_TOOLTIP = "simulado — dado real, custos assumidos, sem dinheiro";

/** "carteira de referência, sem carteira aberta" -- the fixed, labelled fallback when the organization has no principal paper wallet yet (brief T3.17). */
export const REFERENCE_EQUITY_USDT = "10000";

export interface MoneyRuler {
  /** The Decimal string this ruler's risk is a percentage of. */
  equityUsdt: string;
  /** `null` when the wallet has no BRL decomposition yet, or there is no real wallet at all. */
  equityBrl: string | null;
  /** `true` for the fixed 10.000 USDT fallback -- never a real wallet. */
  isReference: boolean;
  /** `equityUsdt * RISK_PER_TRADE_PCT` -- the USDT amount "risked" per simulated operation. */
  riskUsdt: number;
}

function toNum(value: string): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

function computeRiskUsdt(equityUsdt: string): number {
  return toNum(equityUsdt) * RISK_PER_TRADE_PCT;
}

/** "carteira de referência, sem carteira aberta" (brief T3.17) -- used when the organization has no principal paper wallet, or it could not be read. */
export function buildReferenceRuler(): MoneyRuler {
  return {
    equityUsdt: REFERENCE_EQUITY_USDT,
    equityBrl: null,
    isReference: true,
    riskUsdt: computeRiskUsdt(REFERENCE_EQUITY_USDT),
  };
}

/** The organization's real principal paper wallet (`type = "paper" && !is_arena`, `PortfolioSummaryOut`). */
export function buildWalletRuler(equityUsdt: string, equityBrl: string | null): MoneyRuler {
  return { equityUsdt, equityBrl, isReference: false, riskUsdt: computeRiskUsdt(equityUsdt) };
}

export interface MoneyOrReason {
  value: number | null;
  reason: string | null;
}

/** `usdtAmount` converted to BRL through the wallet's own `equity_brl/equity` ratio (brief T3.17) -- `null` when the ruler has no BRL decomposition to convert through. */
export function usdtToBrl(usdtAmount: number, ruler: MoneyRuler): number | null {
  if (ruler.equityBrl === null) return null;
  const equity = toNum(ruler.equityUsdt);
  if (equity === 0) return null;
  return usdtAmount * (toNum(ruler.equityBrl) / equity);
}

export interface RowMoney {
  /** `r_multiple * risk` -- null exactly when `r_multiple` is (with its own `r_multiple_reason`, never a `0`). */
  pnlUsdt: MoneyOrReason;
  /** `risk / |entry - stop| * entry` -- "o que investiu" (o que a operação teria comprado). */
  notionalUsdt: MoneyOrReason;
  /** `exit/entry - 1`, or `null` when either price is missing. */
  pctMove: number | null;
}

/** One row's money translation (brief T3.17 item 2's "quantia simulada"/"resultado simulado"), computed once per row from the declared ruler. */
export function moneyForRow(row: SignalListItemOut, ruler: MoneyRuler): RowMoney {
  const pnlUsdt: MoneyOrReason =
    row.r_multiple !== null ? { value: toNum(row.r_multiple) * ruler.riskUsdt, reason: null } : { value: null, reason: row.r_multiple_reason };

  const entry = row.virtual_entry;
  let notionalUsdt: MoneyOrReason;
  if (entry === null) {
    notionalUsdt = { value: null, reason: row.no_entry_reason ?? row.censored_reason ?? "no_entry" };
  } else if (row.stop === null) {
    notionalUsdt = { value: null, reason: "no_stop" };
  } else {
    const entryNum = toNum(entry);
    const distance = Math.abs(entryNum - toNum(row.stop));
    notionalUsdt = distance === 0 ? { value: null, reason: "zero_stop_distance" } : { value: (ruler.riskUsdt / distance) * entryNum, reason: null };
  }

  const pctMove = entry !== null && row.exit_price !== null && toNum(entry) !== 0 ? toNum(row.exit_price) / toNum(entry) - 1 : null;

  return { pnlUsdt, notionalUsdt, pctMove };
}

/** "Entrou"/"Saiu" cell text: price + short date/time on one line (row height is fixed, docs/DESIGN.md §2 density table). Used by `saidaText`/the signal panel's plain-text rendering; the table's own cells render `LabPriceTimeCell`/`LabExitCell` (two lines) instead. */
export function priceAndTime(price: string | null, ts: string | null): string {
  if (price === null) return "--";
  const when = ts ? formatWhenShort(ts) : null;
  return when ? `${formatPrice(price)} · ${when}` : formatPrice(price);
}

/** "Saiu" column: the real exit (with its own "motivo" -- brief T3.17b item 5), or an honest reason it never resolved (brief T3.17 item 3: "aberta"/"não entrou: motivo"/"censurada: motivo"). */
export function saidaText(row: SignalListItemOut): string {
  if (row.exit_price !== null) return `${priceAndTime(row.exit_price, row.exit_ts)} · motivo: ${EXIT_REASON_LABEL[row.result]}`;
  if (row.tracking_state === "no_entry") return `não entrou: ${reasonLabel(row.no_entry_reason ?? "sem motivo informado")}`;
  if (row.tracking_state === "censored") return `censurada: ${reasonLabel(row.censored_reason ?? "sem motivo informado")}`;
  if (row.tracking_state === "pending_entry" || row.tracking_state === "active") return "aberta";
  return "--";
}

export type ResultBadgeKind = "lucro" | "prejuizo" | "pendente" | "neutro";

/** The three (plus a rare exact-zero fourth) states of the "Resultado" badge (brief T3.17 item 3). */
export function resultBadgeKind(pnlUsdt: number | null): ResultBadgeKind {
  if (pnlUsdt === null) return "pendente";
  if (pnlUsdt > 0) return "lucro";
  if (pnlUsdt < 0) return "prejuizo";
  return "neutro";
}

export interface RowHighlight {
  market: string;
  pnlUsdt: number;
  result: OutcomeResult;
}

export interface RowsSummary {
  total: number;
  /** `tracking_state === "terminal"`. */
  completed: number;
  /** `r_multiple !== null` -- a subset of `completed` (a terminal outcome can still have an unsettleable funding, `funding_not_settleable`). */
  withKnownPnl: number;
  withProfit: number;
  withLoss: number;
  /** `pending_entry | active`. */
  pending: number;
  noEntry: number;
  censored: number;
  resultUsdt: MoneyOrReason;
  resultBrl: MoneyOrReason;
  /** `withProfit / (withProfit + withLoss)` -- ties (an exact-zero pnl) are excluded from both sides, same as the API's own `net_profit_rate`. */
  winRate: MoneyOrReason;
  /** Mean pnl across `withProfit` rows only (brief T3.17b item 1) -- "desta página", the same page-bound scope as every other figure here. */
  avgProfitUsdt: MoneyOrReason;
  /** Mean pnl across `withLoss` rows only -- negative when it has a value. */
  avgLossUsdt: MoneyOrReason;
  best: RowHighlight | null;
  worst: RowHighlight | null;
}

interface Accumulator {
  completed: number;
  withKnownPnl: number;
  withProfit: number;
  withLoss: number;
  pending: number;
  noEntry: number;
  censored: number;
  sumUsdt: number;
  sumBrl: number;
  sumProfitUsdt: number;
  sumLossUsdt: number;
  best: RowHighlight | null;
  worst: RowHighlight | null;
}

const TRACKING_BUCKET: Partial<Record<SignalListItemOut["tracking_state"], keyof Accumulator>> = {
  terminal: "completed",
  pending_entry: "pending",
  active: "pending",
  no_entry: "noEntry",
  censored: "censored",
};

function accumulateRow(acc: Accumulator, row: SignalListItemOut, ruler: MoneyRuler, brlAvailable: boolean): void {
  const bucket = TRACKING_BUCKET[row.tracking_state];
  if (bucket) acc[bucket]++;

  if (row.r_multiple === null) return;
  acc.withKnownPnl++;
  const pnl = toNum(row.r_multiple) * ruler.riskUsdt;
  acc.sumUsdt += pnl;
  if (pnl > 0) {
    acc.withProfit++;
    acc.sumProfitUsdt += pnl;
  } else if (pnl < 0) {
    acc.withLoss++;
    acc.sumLossUsdt += pnl;
  }
  if (brlAvailable) acc.sumBrl += usdtToBrl(pnl, ruler) ?? 0;

  const highlight: RowHighlight = { market: row.market, pnlUsdt: pnl, result: row.result };
  if (acc.best === null || pnl > acc.best.pnlUsdt) acc.best = highlight;
  if (acc.worst === null || pnl < acc.worst.pnlUsdt) acc.worst = highlight;
}

/** Totals card math (brief T3.17 item 2, extended by T3.17b item 1), computed client-side from whatever rows are currently loaded -- never a second server round-trip. */
export function summarizeRows(rows: SignalListItemOut[], ruler: MoneyRuler): RowsSummary {
  const brlAvailable = ruler.equityBrl !== null;
  const acc: Accumulator = {
    completed: 0,
    withKnownPnl: 0,
    withProfit: 0,
    withLoss: 0,
    pending: 0,
    noEntry: 0,
    censored: 0,
    sumUsdt: 0,
    sumBrl: 0,
    sumProfitUsdt: 0,
    sumLossUsdt: 0,
    best: null,
    worst: null,
  };
  for (const row of rows) accumulateRow(acc, row, ruler, brlAvailable);

  const resolvedForRate = acc.withProfit + acc.withLoss;

  return {
    total: rows.length,
    completed: acc.completed,
    withKnownPnl: acc.withKnownPnl,
    withProfit: acc.withProfit,
    withLoss: acc.withLoss,
    pending: acc.pending,
    noEntry: acc.noEntry,
    censored: acc.censored,
    resultUsdt: acc.withKnownPnl > 0 ? { value: acc.sumUsdt, reason: null } : { value: null, reason: "no_completed_operations" },
    resultBrl:
      acc.withKnownPnl === 0
        ? { value: null, reason: "no_completed_operations" }
        : brlAvailable
          ? { value: acc.sumBrl, reason: null }
          : { value: null, reason: "no_brl_wallet" },
    winRate: resolvedForRate > 0 ? { value: acc.withProfit / resolvedForRate, reason: null } : { value: null, reason: "no_completed_operations" },
    avgProfitUsdt: acc.withProfit > 0 ? { value: acc.sumProfitUsdt / acc.withProfit, reason: null } : { value: null, reason: "no_profit_operations" },
    avgLossUsdt: acc.withLoss > 0 ? { value: acc.sumLossUsdt / acc.withLoss, reason: null } : { value: null, reason: "no_loss_operations" },
    best: acc.best,
    worst: acc.worst,
  };
}

export type TotalsScope = "page" | "allClosed";

/**
 * The totals card's own scope-switch heading (brief T3.37, replacing the old
 * `hasMore`-inferred wording from T3.17b item 1): the reader now picks the
 * scope explicitly ("desta página" | "de todas as concluídas") instead of the
 * card guessing from whether the page happened to be truncated -- an
 * inference that read wrong the moment a segment's real total (T3.37's
 * `totals.*`) exceeded the loaded page without the reader knowing it.
 */
export function totalsHeading(scope: TotalsScope, pageCount: number, closedTotal: number): string {
  return scope === "page"
    ? `Resultado das operações desta página (${pageCount})`
    : `Resultado de todas as operações concluídas (${closedTotal})`;
}

/**
 * "De todas as concluídas" scope (brief T3.37, Everton: "se tiver 2 mil
 * operações tem que paginar mas mostrar as 2 mil"): the money side of the
 * totals card's scope switch. Never sums a *page* -- each version's own
 * `metrics.sum_of_hypothetical_r` (`GET /lab/shadow/summary`) is already a
 * whole-dataset aggregate (cohort/window applied), so adding together a
 * handful of *complete* per-version totals is not the mistake the brief
 * warns against (extrapolating a whole-dataset figure from a partial
 * ~200-row page). If any relevant version's own sum is itself unavailable
 * (`value: null`, e.g. no mature sample yet), the combined result is
 * unavailable too -- treating the missing version as a silent zero would
 * understate the real total rather than say so.
 */
export function combineClosedSumRUsdt(versions: VersionSummaryOut[], ruler: MoneyRuler): MoneyOrReason {
  if (versions.length === 0) return { value: null, reason: "no_versions_in_selection" };
  const missing = versions.find((v) => v.metrics.sum_of_hypothetical_r.value === null);
  if (missing) return { value: null, reason: missing.metrics.sum_of_hypothetical_r.reason ?? "no_sample" };
  const totalR = versions.reduce((sum, v) => sum + toNum(v.metrics.sum_of_hypothetical_r.value as string), 0);
  return { value: totalR * ruler.riskUsdt, reason: null };
}

// --- T3.18 scoreboard money (brief item 3: "então os números em dinheiro
// através da régua do T3.17 -- resultado acumulado USDT/BRL, média por
// operação") -- same `R * risco` rule as `moneyForRow`, applied to the
// whole-version `sum_r`/`expectancy_r` the scoreboard API returns instead of
// one row's `r_multiple`. The API never computes money (brief item 1): only
// R multiples and counts cross the wire, and this module is the one and only
// place that turns an R into a ruler-scaled USDT/BRL figure. ---

/** One R-multiple Decimal string converted to USDT through the ruler -- shared by the curve chart's per-point conversion and `scoreboardMoney` below. */
export function rToUsdt(rValue: string, ruler: MoneyRuler): number {
  return toNum(rValue) * ruler.riskUsdt;
}

function decimalOrReasonToUsdt(metric: { value: string | null; reason?: string | null }, ruler: MoneyRuler): MoneyOrReason {
  if (metric.value === null) return { value: null, reason: metric.reason ?? null };
  return { value: rToUsdt(metric.value, ruler), reason: null };
}

function usdtMoneyToBrl(money: MoneyOrReason, ruler: MoneyRuler): MoneyOrReason {
  if (money.value === null) return { value: null, reason: money.reason };
  const brl = usdtToBrl(money.value, ruler);
  return brl !== null ? { value: brl, reason: null } : { value: null, reason: "no_brl_wallet" };
}

export interface ScoreboardMoney {
  /** `sum_r * risk` -- the version's whole simulated result, accumulated over every evaluable outcome. */
  cumulativeUsdt: MoneyOrReason;
  cumulativeBrl: MoneyOrReason;
  /** `expectancy_r * risk` -- the mean simulated result per operation. */
  avgPerOpUsdt: MoneyOrReason;
  avgPerOpBrl: MoneyOrReason;
}

/** The scoreboard card's money block (brief T3.18 item 3), built once per row from the same ruler the rest of the Lab uses. */
export function scoreboardMoney(
  sumR: { value: string | null; reason?: string | null },
  expectancyR: { value: string | null; reason?: string | null },
  ruler: MoneyRuler,
): ScoreboardMoney {
  const cumulativeUsdt = decimalOrReasonToUsdt(sumR, ruler);
  const avgPerOpUsdt = decimalOrReasonToUsdt(expectancyR, ruler);
  return {
    cumulativeUsdt,
    cumulativeBrl: usdtMoneyToBrl(cumulativeUsdt, ruler),
    avgPerOpUsdt,
    avgPerOpBrl: usdtMoneyToBrl(avgPerOpUsdt, ruler),
  };
}
