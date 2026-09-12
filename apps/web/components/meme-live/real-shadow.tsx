/**
 * T4.17 deliverable 4: "o card mostra os dois desfechos lado a lado quando
 * existirem (`mode` da aposta)". `row.bet.mode === "live"` means this same
 * proposal also produced (or is trying to produce) a real order/position on
 * the executor's own ledger -- rendered here beside the paper card, never
 * merged into it. No React state: pure display, safe to import from a
 * `"use client"` file (`open-bets-section.tsx`) without becoming one itself.
 */
import { formatSol } from "@/components/meme/meme-format";
import { formatSolSigned, signClass } from "@/components/meme-desk/meme-desk-format";
import type { MemeDeskRow } from "@/lib/api/meme-desk-types";

import { liveOrderStatusLabel, livePositionStatusLabel } from "./labels";
import type { LiveOutcomeIndex } from "./live-index";
import { executorRefusalLabel } from "./refusal-labels";

export interface RealShadowPanelProps {
  row: MemeDeskRow;
  /** `null` when `GET /meme/live` itself failed to load -- distinct from "loaded, but no matching row yet". */
  live: LiveOutcomeIndex | null;
}

/** Renders nothing for an ordinary paper bet (`row.bet.mode !== "live"`); otherwise the real outcome beside the paper one, or an honest reason there is none yet. */
export function RealShadowPanel({ row, live }: RealShadowPanelProps) {
  if (row.bet?.mode !== "live") return null;

  return (
    <div className="rounded-md border border-red/40 bg-red-soft/20 p-2 text-[11px]">
      <p className="font-semibold text-red">REAL — sombra de uma ordem real</p>
      {live === null ? (
        <p className="text-fg-muted">indisponível: falha ao carregar o executor (/meme/live)</p>
      ) : (
        <RealOutcomeLine row={row} live={live} />
      )}
    </div>
  );
}

function RealOutcomeLine({ row, live }: { row: MemeDeskRow; live: LiveOutcomeIndex }) {
  const outcome = live.get(row.id);
  if (!outcome || (!outcome.position && !outcome.order)) {
    return <p className="text-fg-muted">ainda sem ordem registrada no executor</p>;
  }
  const { position, order } = outcome;
  if (position) {
    return (
      <p className="font-mono tabular-nums text-fg">
        <span className="font-sans text-fg-muted">{livePositionStatusLabel(position.status)}</span>
        {" · marca "}
        {position.mark_sol ? formatSol(position.mark_sol) : "sem marca ainda"}
        {position.pnl_sol ? (
          <>
            {" · PnL "}
            <span className={signClass(position.pnl_sol)}>{formatSolSigned(position.pnl_sol)}</span>
          </>
        ) : null}
      </p>
    );
  }
  if (!order) return null;
  const refusal = order.first_refusal ?? order.reason;
  return (
    <p className="text-fg">
      <span className="font-sans text-fg-muted">{liveOrderStatusLabel(order.status)}</span>
      {refusal ? ` · ${executorRefusalLabel(refusal)}` : ""}
    </p>
  );
}
