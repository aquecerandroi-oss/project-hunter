/**
 * Money-divergence safeguard for a merged sibling-version group (code-review
 * finding 2 on T3.38, closed by T3.38c): once `identity_key` includes `stop`
 * (T3.38c-api's own fix), every member of a `LabSignalGroup` should always
 * agree on `r_multiple` and the money it implies -- a shared entry/exit/
 * result with a different stop distance was the one gap that let two
 * sibling versions decide the exact same operation yet disagree on R. This
 * module is the *display-time* safeguard for the case where members still
 * disagree (a future regression, a hash edge case not yet covered): the
 * screen never silently shows one member's money as if it spoke for the
 * whole group -- it shows the real range and a note instead. Pure, no I/O,
 * same convention as `lab-money.ts`.
 */
import { moneyForRow, type MoneyRuler } from "@/components/lab/lab-money";
import type { LabSignalGroup } from "@/components/lab/lab-signal-grouping";
import type { SignalListItemOut } from "@/lib/api/lab-types";
import { formatUsdtSigned } from "@/lib/format";

export interface MoneyRange {
  min: number;
  max: number;
}

function rangeOfValues(values: (number | null)[]): MoneyRange | null {
  const nums = values.filter((v): v is number => v !== null);
  if (nums.length < 2) return null;
  const min = Math.min(...nums);
  const max = Math.max(...nums);
  // Two members that only disagree past the cent `formatUsdtSigned` itself
  // rounds to would never read as "divergent" on screen -- this never flags
  // noise the reader could not see anyway.
  if (Math.round(min * 100) === Math.round(max * 100)) return null;
  return { min, max };
}

/** `null` when every member's simulated result agrees (the only case once T3.38c-api's `stop` fix is live) or fewer than two members carried a value. */
export function pnlRangeUsdt(members: SignalListItemOut[], ruler: MoneyRuler): MoneyRange | null {
  return rangeOfValues(members.map((m) => moneyForRow(m, ruler).pnlUsdt.value));
}

/** Same safeguard for "quantia simulada" -- driven by `stop` directly, so it can diverge independently of `r_multiple`. */
export function notionalRangeUsdt(members: SignalListItemOut[], ruler: MoneyRuler): MoneyRange | null {
  return rangeOfValues(members.map((m) => moneyForRow(m, ruler).notionalUsdt.value));
}

/** "+34,00 USDT a +41,20 USDT" (finding 2's own example) -- both ends through the same signed formatter every other money figure on this screen uses. */
export function formatMoneyRange(range: MoneyRange): string {
  return `${formatUsdtSigned(range.min)} a ${formatUsdtSigned(range.max)}`;
}

/** The note shown beside a divergent range -- explains why this one operation reads differently than every other merged row. */
export const MONEY_DIVERGENCE_NOTE = "versões irmãs divergem em R/dinheiro para esta operação -- mostrando a faixa em vez da primeira versão carregada";

function groupMoneyDiverges(group: LabSignalGroup, ruler: MoneyRuler): boolean {
  return group.members.length > 1 && (pnlRangeUsdt(group.members, ruler) !== null || notionalRangeUsdt(group.members, ruler) !== null);
}

/** How many loaded groups trip the safeguard above -- the count the totals card's own note spells out; zero in the healthy, expected case. */
export function countDivergentGroups(groups: LabSignalGroup[], ruler: MoneyRuler): number {
  return groups.filter((g) => groupMoneyDiverges(g, ruler)).length;
}
