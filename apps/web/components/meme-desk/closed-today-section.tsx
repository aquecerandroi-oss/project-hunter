import Link from "next/link";

import { formatSol } from "@/components/meme/meme-format";
import type { LiveOutcomeIndex } from "@/components/meme-live/live-index";
import { RealShadowPanel } from "@/components/meme-live/real-shadow";
import { BrasiliaShort } from "@/components/time/brasilia-instant";
import type { MemeDeskRow } from "@/lib/api/meme-desk-types";

import { BetLegBadge, betAnchorId } from "./bet-leg";
import { decisionToFillLabel, exitReasonLabel, outcomeQualityLabel, proposalStatusLabel, refusalLabel } from "./labels";
import { formatR, formatSolSigned, signClass } from "./meme-desk-format";

export interface ClosedTodaySectionProps {
  orgSlug: string;
  rows: MemeDeskRow[];
  /** T4.10b: ids of every bet on the page (see `bet-leg.tsx`). */
  knownBetIds?: readonly string[];
  /** T4.17 deliverable 4: `null` when `GET /meme/live` itself failed. */
  liveOutcomes?: LiveOutcomeIndex | null;
}

/** "Fechadas hoje" (contract §Tela): exit reason, PnL, R, link to `/meme/{mint}`. Server Component -- nothing interactive. */
export function ClosedTodaySection({ orgSlug, rows, knownBetIds = [], liveOutcomes = null }: ClosedTodaySectionProps) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-sm font-medium text-fg">Fechadas hoje</h2>
      {rows.length === 0 ? (
        <p className="rounded-md border border-border p-4 text-sm text-fg-muted">Nenhuma aposta fechada hoje (dia de Brasília).</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {rows.map((row) => {
            const bet = row.bet;
            if (!bet) return null;
            return (
              <li key={bet.id} id={betAnchorId(bet.id)} className="flex flex-col gap-2 rounded-md border border-border p-3 text-xs">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="min-w-0">
                    <Link href={`/${orgSlug}/meme/${row.mint}`} className="text-sm font-medium text-fg hover:underline">
                      {row.token?.name ?? "(nome desconhecido)"}
                    </Link>
                    <span className="ml-2 inline-flex flex-wrap items-baseline gap-2">
                      <BetLegBadge bet={bet} knownBetIds={knownBetIds} />
                    </span>
                    <span className="ml-2 text-fg-muted">
                      {exitReasonLabel(bet.exit_reason)} · saiu {bet.exit_at ? <BrasiliaShort iso={bet.exit_at} /> : "—"}
                      {bet.sol_spent ? ` · entrou com ${formatSol(bet.sol_spent)}` : ""}
                      {decisionToFillLabel(bet.decision_to_fill_s) ? ` · ${decisionToFillLabel(bet.decision_to_fill_s)}` : ""}
                    </span>
                  </span>
                  <span className="font-mono tabular-nums">
                    <span className={signClass(bet.pnl_sol)}>{bet.pnl_sol ? formatSolSigned(bet.pnl_sol) : "PnL não informado"}</span>
                    <span className="ml-2 text-fg-muted" title={bet.outcome_quality === "indeterminate" ? (bet.outcome_quality_reason ?? undefined) : undefined}>
                      {bet.outcome_quality === "indeterminate" ? outcomeQualityLabel(bet.outcome_quality) : bet.r_multiple ? formatR(bet.r_multiple) : ""}
                    </span>
                  </span>
                </div>
                <RealShadowPanel row={row} live={liveOutcomes} />
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

export interface RecentDecisionsSectionProps {
  orgSlug: string;
  rows: MemeDeskRow[];
  limit?: number;
  /** T4.10b: ids of every bet on the page (see `bet-leg.tsx`). */
  knownBetIds?: readonly string[];
}

/** Recent history: rejected/expired/unfilled proposals (with the loop's named refusal -- contract §Semântica 4) and older closes. */
export function RecentDecisionsSection({ orgSlug, rows, limit = 12, knownBetIds = [] }: RecentDecisionsSectionProps) {
  const shown = rows.slice(0, limit);
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-sm font-medium text-fg">Decididas recentemente</h2>
      {shown.length === 0 ? (
        <p className="rounded-md border border-border p-4 text-sm text-fg-muted">Nenhuma decisão anterior registrada.</p>
      ) : (
        <ul className="flex flex-col gap-1">
          {shown.map((row) => {
            const refusal = refusalLabel(row.refusal);
            return (
              <li key={row.id} id={row.bet ? betAnchorId(row.bet.id) : undefined} className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border px-3 py-2 text-xs">
                <span className="min-w-0">
                  <Link href={`/${orgSlug}/meme/${row.mint}`} className="font-medium text-fg hover:underline">
                    {row.token?.name ?? "(nome desconhecido)"}
                  </Link>
                  {row.bet && (
                    <span className="ml-2 inline-flex flex-wrap items-baseline gap-2">
                      <BetLegBadge bet={row.bet} knownBetIds={knownBetIds} />
                    </span>
                  )}
                  <span className="ml-2 text-fg-muted">{proposalStatusLabel(row.status)}</span>
                  {refusal && <span className="ml-2 text-warning">{refusal}</span>}
                  {row.bet?.status === "closed" && row.bet.pnl_sol && <span className={`ml-2 font-mono tabular-nums ${signClass(row.bet.pnl_sol)}`}>{formatSolSigned(row.bet.pnl_sol)}</span>}
                </span>
                <span className="text-fg-subtle">
                  {row.decided_at ? <BrasiliaShort iso={row.decided_at} /> : <BrasiliaShort iso={row.proposed_at} />}
                  {row.decided_by ? ` · ${row.decided_by === "rules" ? "laço" : "operador"}` : ""}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
