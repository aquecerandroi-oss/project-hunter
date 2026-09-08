import { reasonLabel } from "@/components/lab/lab-format";
import type { MoneyOrReason } from "@/components/lab/lab-money";
import { formatMoneyRange, MONEY_DIVERGENCE_NOTE, type MoneyRange } from "@/components/lab/lab-signal-divergence";
import { formatBrlSigned, formatUsdtSigned } from "@/lib/format";

/**
 * A `MoneyOrReason` rendered as its signed USDT text, or the reason in muted
 * text (SHADOW-LAB.md §9: never a fabricated `0`) -- the "Quantia simulada"
 * cell's own value, split out so `LabSignalRow`'s function stays under the
 * lint config's cyclomatic-complexity budget.
 */
export function LabMoneyOrReason({ money }: { money: MoneyOrReason }) {
  if (money.value === null) return <span className="text-fg-muted">{reasonLabel(money.reason ?? "sem motivo informado")}</span>;
  return <>{formatUsdtSigned(money.value)}</>;
}

/** "Resultado": USDT + its BRL companion (when known), or the reason pnl is unknown -- same split-out purpose as `LabMoneyOrReason` above. */
export function LabResultValue({ pnlUsdt, pnlBrl }: { pnlUsdt: MoneyOrReason; pnlBrl: number | null }) {
  if (pnlUsdt.value === null) return <span className="text-fg-muted">{reasonLabel(pnlUsdt.reason ?? "sem motivo informado")}</span>;
  return (
    <span className="font-mono tabular-nums text-fg">
      {formatUsdtSigned(pnlUsdt.value)}
      {pnlBrl !== null && <span className="text-fg-muted"> ({formatBrlSigned(pnlBrl)})</span>}
    </span>
  );
}

/**
 * Renders instead of `LabResultValue`/`LabMoneyOrReason` when a merged
 * group's members disagree on the money figure (finding 2 of the T3.38
 * review) -- the real range plus a one-line note, never a single value
 * standing in for the whole group.
 */
export function LabMoneyRangeValue({ range }: { range: MoneyRange }) {
  return (
    <span className="font-mono tabular-nums text-fg" title={MONEY_DIVERGENCE_NOTE}>
      {formatMoneyRange(range)}
      <span className="ml-1 text-[10px] font-sans font-normal text-warning">(faixa)</span>
    </span>
  );
}
