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

import { reasonLabel } from "@/components/lab/lab-format";
import { formatPrice } from "@/components/markets/format";
import type { SignalListItemOut } from "@/lib/api/lab-types";
import { formatUtc } from "@/lib/format";

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

/** "Entrou"/"Saiu" cell text: price + hour on one line (row height is fixed, docs/DESIGN.md §2 density table). */
export function priceAndTime(price: string | null, ts: string | null): string {
  if (price === null) return "--";
  return ts ? `${formatPrice(price)} · ${formatUtc(ts)}` : formatPrice(price);
}

/** "Saiu" column: the real exit, or an honest reason it never resolved (brief T3.17 item 3: "aberta"/"não entrou: motivo"/"censurada: motivo"). */
export function saidaText(row: SignalListItemOut): string {
  if (row.exit_price !== null) return priceAndTime(row.exit_price, row.exit_ts);
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
  if (pnl > 0) acc.withProfit++;
  else if (pnl < 0) acc.withLoss++;
  if (brlAvailable) acc.sumBrl += usdtToBrl(pnl, ruler) ?? 0;
}

/** Totals card math (brief T3.17 item 2), computed client-side from whatever rows are currently loaded -- never a second server round-trip. */
export function summarizeRows(rows: SignalListItemOut[], ruler: MoneyRuler): RowsSummary {
  const brlAvailable = ruler.equityBrl !== null;
  const acc: Accumulator = { completed: 0, withKnownPnl: 0, withProfit: 0, withLoss: 0, pending: 0, noEntry: 0, censored: 0, sumUsdt: 0, sumBrl: 0 };
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
  };
}

/** "das N operações listadas" (brief T3.17 item 2) -- only when the list is truncated (a `next_cursor` exists), so totals never silently claim to cover more than what is actually on screen. */
export function truncationNote(rowCount: number, hasMore: boolean): string | null {
  return hasMore ? `calculado das ${rowCount} operações listadas -- há mais sinais além desta página` : null;
}
