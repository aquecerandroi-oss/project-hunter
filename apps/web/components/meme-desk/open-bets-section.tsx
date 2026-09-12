"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { formatSol } from "@/components/meme/meme-format";
import { BrasiliaShort } from "@/components/time/brasilia-instant";
import { Button } from "@/components/ui/button";
import { computeAgeMs, formatAge, useAgeTicker } from "@/hooks/useAgeTicker";
import { sellNowAction } from "@/lib/api/meme-desk-actions";
import type { MemeDeskBet, MemeDeskRow } from "@/lib/api/meme-desk-types";

import { BetLegBadge, betAnchorId } from "./bet-leg";
import { memeDeskProblemMessage } from "./labels";
import { formatMultiple, formatR, formatSolSigned, remainingHoldLabel, signClass } from "./meme-desk-format";

const SELL_WARNING = "vende na próxima fotografia, não neste preço";

interface SellNowConfirmProps {
  bet: MemeDeskBet;
  busy: boolean;
  onConfirm: () => void;
  onBack: () => void;
}

/** One-tap confirmation (contract §Tela): the last snapshot's mark and the warning, then one destructive confirm. */
function SellNowConfirm({ bet, busy, onConfirm, onBack }: SellNowConfirmProps) {
  return (
    <div className="flex flex-col gap-2 rounded-md border border-red/40 bg-red-soft/40 p-3 text-xs">
      <p className="text-fg">
        Última fotografia: {bet.mark_sol ? formatSol(bet.mark_sol) : "sem marca ainda"}
        {bet.mark_at ? (
          <>
            {" "}
            em <BrasiliaShort iso={bet.mark_at} />
          </>
        ) : null}
      </p>
      <p className="font-medium text-red">Atenção: {SELL_WARNING}.</p>
      <div className="flex gap-2">
        <Button type="button" size="sm" variant="destructive" onClick={onConfirm} disabled={busy}>
          {busy ? "Enviando..." : "Confirmar venda (papel)"}
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={onBack} disabled={busy}>
          Voltar
        </Button>
      </div>
    </div>
  );
}

function BetHeader({ orgSlug, row, bet, knownBetIds }: { orgSlug: string; row: MemeDeskRow; bet: MemeDeskBet; knownBetIds: readonly string[] }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-2">
      <span className="flex flex-wrap items-baseline gap-2">
        <Link href={`/${orgSlug}/meme/${row.mint}`} className="text-sm font-medium text-fg hover:underline">
          {row.token?.name ?? "(nome desconhecido)"}
        </Link>
        <BetLegBadge bet={bet} knownBetIds={knownBetIds} />
      </span>
      <span className="text-[11px] text-fg-subtle">
        entrada <BrasiliaShort iso={bet.entry_at} /> · {bet.sol_spent ? formatSol(bet.sol_spent) : "gasto não informado"}
        {row.rule_set ? ` · ${row.rule_set.name} v${row.rule_set.version}` : ""}
      </span>
    </div>
  );
}

/** Live mark, unrealized PnL/R (computed by the API in Decimal) and the remaining hold -- every absent value is named, never a zero. */
function BetMetrics({ bet, nowMs }: { bet: MemeDeskBet; nowMs: number }) {
  const markAge = computeAgeMs(bet.mark_at, nowMs);
  const exitPlan = [
    bet.params.target_x ? `alvo ${formatMultiple(bet.params.target_x)}` : "alvo não informado",
    bet.params.trailing_pct ? `trailing ${bet.params.trailing_pct}%` : null,
    bet.high_water_x ? `máxima ${formatMultiple(bet.high_water_x)}` : null,
  ].filter((p): p is string => p !== null);
  return (
    <div className="grid grid-cols-2 gap-2 font-mono text-xs tabular-nums sm:grid-cols-4">
      <div>
        <p className="text-[11px] font-sans text-fg-muted">Marca (SOL)</p>
        <p className="text-fg">{bet.mark_sol ? formatSol(bet.mark_sol) : "sem marca ainda"}</p>
        <p className="font-sans text-[11px] text-fg-subtle">{markAge === null ? "sem fotografia ainda" : `Atualizado há ${formatAge(markAge)}`}</p>
      </div>
      <div>
        <p className="text-[11px] font-sans text-fg-muted">PnL (não realizado)</p>
        <p className={signClass(bet.unrealized_pnl_sol)}>{bet.unrealized_pnl_sol ? formatSolSigned(bet.unrealized_pnl_sol) : "sem marca ainda"}</p>
      </div>
      <div>
        <p className="text-[11px] font-sans text-fg-muted">R</p>
        <p className={signClass(bet.unrealized_r)}>{bet.unrealized_r ? formatR(bet.unrealized_r) : "—"}</p>
      </div>
      <div>
        <p className="text-[11px] font-sans text-fg-muted">Espera</p>
        <p className="text-fg">{remainingHoldLabel(bet.hold_deadline_at, nowMs)}</p>
        <p className="font-sans text-[11px] text-fg-subtle">{exitPlan.join(" · ")}</p>
      </div>
    </div>
  );
}

function BetCard({ orgSlug, row, bet, knownBetIds, nowMs, canOperate, confirming, busy, onSell, onConfirm, onBack }: { orgSlug: string; row: MemeDeskRow; bet: MemeDeskBet; knownBetIds: readonly string[]; nowMs: number; canOperate: boolean; confirming: boolean; busy: boolean; onSell: () => void; onConfirm: () => void; onBack: () => void }) {
  return (
    <li id={betAnchorId(bet.id)} className="flex flex-col gap-2 rounded-md border border-border p-3">
      <BetHeader orgSlug={orgSlug} row={row} bet={bet} knownBetIds={knownBetIds} />
      <BetMetrics bet={bet} nowMs={nowMs} />
      {confirming ? (
        <SellNowConfirm bet={bet} busy={busy} onConfirm={onConfirm} onBack={onBack} />
      ) : (
        <div className="flex items-center gap-2">
          <Button type="button" size="sm" variant="outline" onClick={onSell} disabled={!canOperate || busy} title={!canOperate ? "Requer o papel Trader ou superior nesta organização." : undefined}>
            Vender agora
          </Button>
          <span className="text-[11px] text-fg-subtle">{SELL_WARNING}</span>
        </div>
      )}
    </li>
  );
}

export interface OpenBetsSectionProps {
  orgId: string;
  orgSlug: string;
  rows: MemeDeskRow[];
  serverNow: string;
  canOperate: boolean;
  /** T4.10b: ids of every bet on the page, so a scale leg links to its probe only when the probe's card exists. */
  knownBetIds?: string[];
}

/** "Abertas" (contract §Tela): live mark, PnL, R, remaining hold, and "Vender agora" with a one-tap confirmation. */
export function OpenBetsSection({ orgId, orgSlug, rows, serverNow, canOperate, knownBetIds = [] }: OpenBetsSectionProps) {
  const router = useRouter();
  const { now } = useAgeTicker(serverNow);
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // One `Idempotency-Key` per "Vender agora" gesture, reused across retries
  // of that same confirmation and dropped on success/"Voltar" -- a ref, read
  // and written only inside event handlers, never during render.
  const keysRef = useRef<Map<string, string>>(new Map());

  function keyFor(betId: string): string {
    const existing = keysRef.current.get(betId);
    if (existing) return existing;
    const fresh = crypto.randomUUID();
    keysRef.current.set(betId, fresh);
    return fresh;
  }

  async function confirm(betId: string): Promise<void> {
    setError(null);
    setBusyId(betId);
    try {
      const result = await sellNowAction(orgId, betId, keyFor(betId));
      if (!result.ok) {
        setError(memeDeskProblemMessage(result.problem));
        return;
      }
      keysRef.current.delete(betId);
      setConfirmingId(null);
      router.refresh();
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-sm font-medium text-fg">Abertas</h2>
      {rows.length === 0 ? (
        <p className="rounded-md border border-border p-4 text-sm text-fg-muted">Nenhuma aposta aberta agora.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {rows.map((row) =>
            row.bet ? (
              <BetCard
                key={row.bet.id}
                orgSlug={orgSlug}
                row={row}
                bet={row.bet}
                knownBetIds={knownBetIds}
                nowMs={now}
                canOperate={canOperate}
                confirming={confirmingId === row.bet.id}
                busy={busyId === row.bet.id}
                onSell={() => setConfirmingId(row.bet?.id ?? null)}
                onConfirm={() => void confirm(row.bet?.id ?? "")}
                onBack={() => {
                  if (row.bet) keysRef.current.delete(row.bet.id);
                  setConfirmingId(null);
                }}
              />
            ) : null,
          )}
        </ul>
      )}
      {error && <p className="text-sm text-red">{error}</p>}
    </section>
  );
}
