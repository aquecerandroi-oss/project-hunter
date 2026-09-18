/**
 * "Carteira real" §1 "Dinheiro agora" (T4.57): chain-fresh SOL, the
 * treasury's USDC, the totals in US$/R$, and what is locked vs. free. Server
 * Component-shaped (no hooks) -- rendered inside the client poll wrapper
 * (`wallet-summary-panel.tsx`) same as `live-executor-panel.tsx`'s blocks.
 */
import { formatSol } from "@/components/meme/meme-format";
import { formatBrl, formatMoney } from "@/lib/format";

import type { WalletNow } from "@/lib/api/meme-live-wallet-types";
import { fxNote, stalenessNote, walletReasonLabel } from "./wallet-summary-format";

function Stat({ label, value, note }: { label: string; value: string; note?: string | null }) {
  return (
    <div className="flex flex-col gap-0.5">
      <p className="text-[11px] font-medium uppercase text-fg-muted">{label}</p>
      <p className="font-mono text-lg tabular-nums text-fg">{value}</p>
      {note && <p className="text-[11px] text-fg-subtle">{note}</p>}
    </div>
  );
}

export function WalletSummaryNow({ now }: { now: WalletNow }) {
  const solValue = now.wallet_sol_balance !== null ? formatSol(now.wallet_sol_balance) : walletReasonLabel(now.wallet_sol_balance_reason);
  const usdcValue = now.wallet_usdc_balance !== null ? `${formatMoney(now.wallet_usdc_balance, { decimals: 2 }).replace(/^\$/, "")} USDC` : walletReasonLabel(now.wallet_usdc_balance_reason);
  const totalUsd = now.total_usd !== null ? formatMoney(now.total_usd, { decimals: 2 }) : walletReasonLabel(now.total_usd_reason);
  const totalBrl = now.total_brl !== null ? formatBrl(now.total_brl) : walletReasonLabel(now.total_brl_reason);
  const locked = formatSol(now.open_marked_sol);
  const reserve = now.reserve_sol !== null ? formatSol(now.reserve_sol) : walletReasonLabel(now.reserve_sol_reason);

  return (
    <div className="flex flex-col gap-3">
      <h3 className="text-xs font-semibold uppercase text-fg-muted">Dinheiro agora</h3>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="SOL na carteira" value={solValue} note={stalenessNote(now.wallet_balance_stale_s)} />
        <Stat label="USDC na tesouraria" value={usdcValue} />
        <Stat label="Total em US$" value={totalUsd} note={now.sol_usd === null ? walletReasonLabel(now.sol_usd_reason) : null} />
        <Stat label="Total em R$" value={totalBrl} note={now.total_brl !== null ? fxNote(now.fx) : null} />
      </div>
      <p className="text-xs text-fg-muted">
        <span className="font-mono tabular-nums text-fg">{now.open_positions}</span> posição(ões) aberta(s) ·{" "}
        <span className="font-mono tabular-nums text-fg">{locked}</span> travados (marcado)
        {now.open_unmarked_positions > 0 && ` · ${now.open_unmarked_positions} sem marca ainda`} · reserva{" "}
        <span className="font-mono tabular-nums text-fg">{reserve}</span>
      </p>
    </div>
  );
}
