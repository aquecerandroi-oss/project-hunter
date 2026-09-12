import { formatSol } from "@/components/meme/meme-format";
import { BrasiliaShort } from "@/components/time/brasilia-instant";
import type { MemeDeskRuleSetBalance, MemeDeskSummary, MemeLoopState } from "@/lib/api/meme-desk-types";

import { ruleSetKindLabel } from "./labels";
import { formatSolSigned, loopStateLabel, signClass, solToUsd } from "./meme-desk-format";

function LoopChip({ loop, serverNow }: { loop: MemeLoopState; serverNow: string }) {
  const state = loopStateLabel(loop, new Date(serverNow).getTime());
  const dot = state.tone === "alive" ? "bg-green" : state.tone === "stopped" ? "bg-red" : "bg-fg-subtle";
  return (
    <span className="inline-flex items-center gap-2 text-xs text-fg-muted">
      <span aria-hidden="true" className={`inline-block size-2 rounded-full ${dot}`} />
      {state.label}
    </span>
  );
}

function UsdLine({ sol, summary }: { sol: string | null; summary: MemeDeskSummary }) {
  if (sol === null) return null;
  if (!summary.sol_usd) return <p className="text-[11px] text-fg-subtle">US$: sem cotação observada pelo laço ainda</p>;
  return (
    <p className="text-[11px] text-fg-subtle">
      ≈ {solToUsd(sol, summary.sol_usd.rate)} · cotação observada em <BrasiliaShort iso={summary.sol_usd.observed_at} />
      {summary.sol_usd.source ? ` (${summary.sol_usd.source})` : ""}
    </p>
  );
}

function RuleSetCard({ balance, summary }: { balance: MemeDeskRuleSetBalance; summary: MemeDeskSummary }) {
  const rs = balance.rule_set;
  return (
    <div className="flex flex-col gap-1 rounded-md border border-border p-4">
      <span className="text-xs font-medium uppercase tracking-wide text-fg-muted">
        {rs.name} v{rs.version}
      </span>
      <span className="text-[11px] text-fg-subtle">{ruleSetKindLabel(rs.kind)}</span>
      {balance.balance_sol === null ? (
        <span className="text-sm text-fg-subtle">saldo de papel: sem saldo inicial no conjunto</span>
      ) : (
        <span className="font-mono text-2xl font-semibold tabular-nums text-fg">{formatSol(balance.balance_sol)}</span>
      )}
      <UsdLine sol={balance.balance_sol} summary={summary} />
      <p className="text-[11px] text-fg-muted">
        {balance.open_bets} aberta(s) · {formatSol(balance.open_sol)} em jogo · dia{" "}
        <span className={`font-mono tabular-nums ${signClass(balance.realized_today_sol)}`}>{formatSolSigned(balance.realized_today_sol)}</span> (
        {balance.closed_today} fechada(s))
      </p>
    </div>
  );
}

export interface DeskOverviewStripProps {
  summary: MemeDeskSummary;
  loop: MemeLoopState;
  serverNow: string;
}

/**
 * Contract §Tela's strip: paper balance per rule set (SOL, and US$ at the
 * quote the loop last observed -- with when), the day's realized PnL, and
 * the loop's state. A missing quote or a set without `wallet_max_sol` says
 * so; nothing here is a live price.
 */
export function DeskOverviewStrip({ summary, loop, serverNow }: DeskOverviewStripProps) {
  return (
    <section className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-fg">
          PnL do dia (realizado, todos os conjuntos):{" "}
          <span className={`font-mono tabular-nums ${signClass(summary.day_pnl_sol)}`}>{formatSolSigned(summary.day_pnl_sol)}</span>
        </p>
        <LoopChip loop={loop} serverNow={serverNow} />
      </div>
      {summary.rule_sets.length === 0 ? (
        <p className="rounded-md border border-border p-4 text-sm text-fg-muted">Nenhum conjunto de regras ativo ainda — o laço cria o primeiro na migração.</p>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {summary.rule_sets.map((balance) => (
            <RuleSetCard key={balance.rule_set.id} balance={balance} summary={summary} />
          ))}
        </div>
      )}
    </section>
  );
}
