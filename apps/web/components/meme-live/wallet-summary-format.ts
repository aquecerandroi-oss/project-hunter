/**
 * Pure formatting for "Carteira real" (T4.57): no React, no fetch --
 * `tests/wallet-summary-format.test.ts`. Every function reads its input
 * defensively, the same convention as `live-format.ts` -- a missing/`null`
 * field renders its own honest note, never a fabricated number.
 */
import { formatSol } from "@/components/meme/meme-format";
import { formatBrl } from "@/lib/format";
import { formatBrasiliaShort } from "@/lib/time";

import { executorStatusLabel } from "./labels";

/** `formatSol` with an explicit leading "+" on a non-zero, non-negative amount (docs/DESIGN.md §2), mirroring `lib/format.ts`'s `formatBrlSigned`/`formatUsdtSigned` -- there is no shared "signed SOL" helper yet, kept local to this panel rather than widening `meme-format.ts`'s surface for one caller. */
export function formatSolSigned(value: string): string {
  const isZero = /^[+-]?0+(\.0+)?$/.test(value.trim());
  const negative = value.trim().startsWith("-");
  const sign = isZero || negative ? "" : "+";
  return `${sign}${formatSol(value)}`;
}

/** `formatBrl` with an explicit leading "+" -- same convention as `formatSolSigned` above, for BRL PnL figures the panel signs (never `formatBrlSigned` from `lib/format.ts` directly on a value that might be `null`). */
export function formatBrlSigned(value: string): string {
  const isZero = /^[+-]?0+(\.0+)?$/.test(value.trim());
  const negative = value.trim().startsWith("-");
  const sign = isZero || negative ? "" : "+";
  return `${sign}${formatBrl(value)}`;
}

/** The reason vocabulary `services/meme_live_wallet.py` names (DESIGN-5: no enum value reaches the screen raw). */
const REASON_LABEL: Record<string, string> = {
  no_wallet_balance: "sem leitura da carteira",
  no_sol_usd_quote: "sem cotação SOL/USD do radar",
  no_fx_quote: "sem câmbio USD/BRL",
  no_open_positions: "nenhuma posição aberta agora",
  positions_without_mark: "há posições abertas ainda sem marca",
  no_closed_positions: "nenhuma posição fechada ainda",
  no_starting_equity_reading: "sem leitura inicial da carteira",
  no_treasury_reading: "sem leitura da tesouraria",
  no_daily_loss_reading: "sem leitura da perda do dia",
};

export function walletReasonLabel(reason: string | null | undefined): string {
  if (!reason) return "sem motivo registrado";
  return REASON_LABEL[reason] ?? `motivo não previsto: ${reason}`;
}

export function walletExecutorStatusNote(status: string): string {
  return executorStatusLabel(status);
}

/** "câmbio de 14:32" (fresh) or "câmbio de 14:32 (última leitura disponível)" (stale) or the named absence -- never a rate with no time attached. */
export function fxNote(fx: { usd_brl: string | null; observed_at: string | null; stale: boolean; reason?: string | null }): string {
  if (fx.usd_brl === null || fx.observed_at === null) return walletReasonLabel(fx.reason);
  const time = formatBrasiliaShort(fx.observed_at) ?? fx.observed_at;
  return fx.stale ? `câmbio de ${time} (última leitura disponível)` : `câmbio de ${time}`;
}

const STARTING_EQUITY_SOURCE_LABEL: Record<string, string> = {
  kill_switch_anchor: "início do dia registrado hoje",
  first_treasury_swap: "primeira leitura de carteira registrada (troca da tesouraria)",
};

export function startingEquitySourceLabel(source: string | null | undefined): string | null {
  if (!source) return null;
  return STARTING_EQUITY_SOURCE_LABEL[source] ?? source;
}

/** Semantic color for a signed SOL/BRL amount (docs/DESIGN.md §2: PnL > 0 is green, PnL < 0 is red, an absent value is `fg-muted`, never colored as if positive) -- same convention as `components/lab/lab-totals-card.tsx`'s `moneyColor`. Reads the string's own sign rather than `Number()` so an amount too precise for a float still colors correctly. */
export function pnlColorClass(value: string | null | undefined): string {
  if (value === null || value === undefined) return "text-fg-muted";
  const trimmed = value.trim();
  if (/^[+-]?0+(\.0+)?$/.test(trimmed)) return "text-fg";
  return trimmed.startsWith("-") ? "text-red" : "text-green";
}

/** "atualizado há 2 s" from the executor's own `wallet_balance_stale_s` (already an age in seconds, never `null` unless the executor never read a balance at all). */
export function stalenessNote(staleS: string | null | undefined): string {
  if (staleS === null || staleS === undefined) return "sem leitura";
  const seconds = Number(staleS);
  if (!Number.isFinite(seconds)) return "sem leitura";
  return `atualizado há ${Math.round(seconds)} s`;
}

/** "aberta há 3min" / "fechada há 2h" -- coarse, no client ticker (the panel re-polls every 10 s and this is computed fresh each time against the response's own `server_now`). */
export function ageSince(iso: string, nowMs: number): string {
  const ts = new Date(iso).getTime();
  if (Number.isNaN(ts)) return "sem leitura";
  const ms = Math.max(0, nowMs - ts);
  const seconds = Math.floor(ms / 1000);
  if (seconds < 60) return `${seconds} s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  return `${hours} h`;
}
