/**
 * Pure helpers for the meme arms board (`meme-arms-board.tsx`, `meme-arm-card.tsx`):
 * decimal-safe sums over a rule set's window of days, the average result per
 * evaluable bet, and the board's own ordering. No React, no fetch --
 * `tests/meme-arms-format.test.ts`.
 */
import { splitDecimal } from "@/components/meme-desk/meme-desk-format";
import type { MemeLabDayScore, MemeLabRuleSetBoard } from "@/lib/api/meme-lab-types";

/** Exact sum of decimal strings (`BigInt`, same parser as `multiplyDecimalStrings`) -- never `Number()` over money. `[]` sums to `"0"`, never a crash. */
export function sumDecimalStrings(values: readonly string[]): string {
  if (values.length === 0) return "0";
  const parts = values.map(splitDecimal);
  const scale = Math.max(...parts.map((p) => p.scale));
  const total = parts.reduce((sum, p) => {
    const scaled = BigInt(p.digits) * 10n ** BigInt(scale - p.scale);
    return sum + (p.negative ? -scaled : scaled);
  }, 0n);
  const negative = total < 0n;
  const abs = negative ? -total : total;
  const raw = abs.toString().padStart(scale + 1, "0");
  const intDigits = raw.slice(0, raw.length - scale) || "0";
  const text = scale > 0 ? `${intDigits}.${raw.slice(raw.length - scale)}` : intDigits;
  return `${negative ? "-" : ""}${text}`;
}

export interface MemeArmWindowTotals {
  /** `Σ bets` over every day on record in the window -- for a pullback arm, every one of these already required a pullback touch (T4.91: the arm is only proposed by the event lane once armed). */
  entries: number;
  /** `Σ closed` -- **includes** `indeterminate` (`meme_lab_scoreboard_v1`'s own `closed` counts every closed bet; only `pnl_sol`/`wins`/`r_sum` are pre-filtered to `measured`, Astra review 2026-09-25 must-fix 1). Never divide a sum by this alone. */
  closed: number;
  /** `measured` wins only (the view's own `WHERE b.measured` filter). */
  wins: number;
  /** T4.16 (`0030`): closes the instrument could not price -- already out of `netSol`/`rSum`/`wins`, counted apart. */
  indeterminate: number;
  /** Exact sum of each day's `pnl_sol.value` (measured closes only) -- a day with none (no closed bets that day) contributes nothing, never a fabricated 0 that would look like a flat day. */
  netSol: string;
  /** Exact sum of each day's `r_sum.value` (measured closes only), same absence discipline as `netSol`. */
  rSum: string;
}

export function sumWindow(days: readonly MemeLabDayScore[]): MemeArmWindowTotals {
  let entries = 0;
  let closed = 0;
  let wins = 0;
  let indeterminate = 0;
  const pnlValues: string[] = [];
  const rValues: string[] = [];
  for (const d of days) {
    entries += d.bets;
    closed += d.closed;
    wins += d.wins;
    indeterminate += d.indeterminate;
    if (d.pnl_sol.value !== null) pnlValues.push(d.pnl_sol.value);
    if (d.r_sum.value !== null) rValues.push(d.r_sum.value);
  }
  return { entries, closed, wins, indeterminate, netSol: sumDecimalStrings(pnlValues), rSum: sumDecimalStrings(rValues) };
}

/** `closed − indeterminate`: the count `netSol`/`rSum`/`wins` are actually averages over (Astra must-fix 1 -- `closed` alone overcounts the denominator by every indeterminate close). */
export function evaluableClosed(totals: Pick<MemeArmWindowTotals, "closed" | "indeterminate">): number {
  return totals.closed - totals.indeterminate;
}

/**
 * The window's average R-multiple per evaluable bet (`rSum / evaluable`) --
 * R is already PnL normalized by the bet's own `initial_risk_sol` at write
 * time (`meme_paper_bets.r_multiple`), so this holds even across a probe +
 * scale leg pair of different sizes (Astra must-fix 2: a fixed-stake
 * percentage does not). `null` without an evaluable bet, never a division
 * by zero. Display-only arithmetic (never money storage) -- the exact SOL
 * amount stays a decimal string (`sumWindow().netSol`), formatted with
 * `formatSolSigned`.
 */
export function avgR(rSum: string, evaluable: number): number | null {
  if (evaluable <= 0) return null;
  const r = Number(rSum);
  return Number.isFinite(r) ? r / evaluable : null;
}

/** Active rule sets first (the Placar's own ordering, `lab/page.tsx`), then alphabetical by `name`/`version` -- deterministic, no "most recent" guess over a set that may not have bet today. */
export function sortRuleSets(rows: readonly MemeLabRuleSetBoard[]): MemeLabRuleSetBoard[] {
  return [...rows].sort((a, b) => {
    if (a.status !== b.status) return a.status === "active" ? -1 : 1;
    return a.name === b.name ? a.version.localeCompare(b.version) : a.name.localeCompare(b.name);
  });
}
