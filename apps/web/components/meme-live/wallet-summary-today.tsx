/**
 * "Carteira real" §2 "Hoje" (T4.57, since 00:00 America/Sao_Paulo): compras,
 * vendas, ganhas/perdidas, PnL realizado e aberto, taxas/aluguel, trocas da
 * tesouraria, e os dois freios (perda do dia vs. teto, escopo restante).
 */
import { formatSol } from "@/components/meme/meme-format";

import type { WalletToday } from "@/lib/api/meme-live-wallet-types";
import { formatBrlSigned, formatSolSigned, pnlColorClass, walletReasonLabel } from "./wallet-summary-format";

function DailyLossBar({ lossSol, capSol }: { lossSol: string | null; capSol: string | null }) {
  if (lossSol === null || capSol === null) {
    return <p className="text-xs text-fg-muted">Perda do dia: {walletReasonLabel("no_daily_loss_reading")}</p>;
  }
  const loss = Number(lossSol);
  const cap = Number(capSol);
  const pct = cap > 0 ? Math.min(100, Math.max(0, (loss / cap) * 100)) : 0;
  const barColor = pct >= 100 ? "bg-red" : pct >= 70 ? "bg-warning" : "bg-green";
  return (
    <div className="flex flex-col gap-1">
      <p className="text-xs text-fg-muted">
        Perda do dia: <span className="font-mono tabular-nums text-fg">{formatSol(lossSol)}</span> de{" "}
        <span className="font-mono tabular-nums text-fg">{formatSol(capSol)}</span>
      </p>
      <div role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100} aria-label="Perda do dia contra o teto" className="h-2 w-full overflow-hidden rounded-full bg-bg-overlay">
        <div className={`h-full rounded-full ${barColor}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export function WalletSummaryToday({ today }: { today: WalletToday }) {
  const openPnl = today.open_pnl_sol !== null ? formatSolSigned(today.open_pnl_sol) : walletReasonLabel(today.open_pnl_sol_reason);
  const realizedBrl = today.realized_pnl_brl !== null ? formatBrlSigned(today.realized_pnl_brl) : walletReasonLabel(today.realized_pnl_brl_reason);

  return (
    <div className="flex flex-col gap-3">
      <h3 className="text-xs font-semibold uppercase text-fg-muted">Hoje</h3>
      <p className="text-xs text-fg-muted">
        compras <span className="font-mono tabular-nums text-fg">{today.bought}</span> · vendas{" "}
        <span className="font-mono tabular-nums text-fg">{today.sold}</span> · ganhas{" "}
        <span className="font-mono tabular-nums text-green">{today.won}</span> · perdidas{" "}
        <span className="font-mono tabular-nums text-red">{today.lost}</span>
      </p>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div>
          <p className="text-[11px] font-medium uppercase text-fg-muted">PnL realizado</p>
          <p className={`font-mono text-base tabular-nums ${pnlColorClass(today.realized_pnl_sol)}`}>{formatSolSigned(today.realized_pnl_sol)}</p>
          <p className="text-[11px] text-fg-subtle">{realizedBrl}</p>
        </div>
        <div>
          <p className="text-[11px] font-medium uppercase text-fg-muted">PnL aberto</p>
          <p className={`font-mono text-base tabular-nums ${pnlColorClass(today.open_pnl_sol)}`}>{openPnl}</p>
        </div>
        <div>
          <p className="text-[11px] font-medium uppercase text-fg-muted">Taxas + aluguel</p>
          <p className="font-mono text-base tabular-nums text-fg">{formatSol(today.fees_sol)}</p>
          <p className="text-[11px] text-fg-subtle">aluguel líquido {formatSol(today.rent_sol)}</p>
        </div>
        <div>
          <p className="text-[11px] font-medium uppercase text-fg-muted">Tesouraria hoje</p>
          <p className="font-mono text-base tabular-nums text-fg">{today.treasury_swaps} troca(s)</p>
          <p className="text-[11px] text-fg-subtle">
            {today.treasury_usdc_spent} USDC → {formatSol(today.treasury_sol_bought)}
          </p>
        </div>
      </div>
      <DailyLossBar lossSol={today.daily_loss_sol} capSol={today.daily_loss_cap_sol} />
      <p className="text-xs text-fg-muted">Escopo restante (teste pequeno): {today.small_test_remaining_sol !== null ? formatSol(today.small_test_remaining_sol) : "sem leitura"}</p>
    </div>
  );
}
