import { reasonLabel } from "@/components/lab/lab-format";
import type { MoneyOrReason } from "@/components/lab/lab-money";
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
