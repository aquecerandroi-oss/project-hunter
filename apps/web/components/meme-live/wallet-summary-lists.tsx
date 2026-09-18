/**
 * "Carteira real" §4 -- the compact lists: today's closed positions (hora,
 * moeda, R, SOL, motivo da saída) and the open ones (hora, moeda, marcado
 * agora, tempo aberto). Two honest empty states (DESIGN.md §2: "nada
 * aconteceu ainda" for the day, distinct wording per list).
 */
import { formatSol } from "@/components/meme/meme-format";
import { exitReasonLabel } from "@/components/meme-desk/labels";
import { BrasiliaShort } from "@/components/time/brasilia-instant";

import type { WalletClosedPosition, WalletOpenPosition } from "@/lib/api/meme-live-wallet-types";
import { truncateAddress } from "./live-format";
import { ageSince, formatSolSigned, pnlColorClass } from "./wallet-summary-format";

function RValue({ r }: { r: string | null }) {
  if (r === null) return <span className="text-fg-muted">—</span>;
  const n = Number(r);
  const text = Number.isFinite(n) ? `${n >= 0 ? "+" : ""}${n.toFixed(2)}R` : `${r}R`;
  return <span className={pnlColorClass(r)}>{text}</span>;
}

function ClosedRow({ position }: { position: WalletClosedPosition }) {
  return (
    <li className="flex flex-wrap items-center justify-between gap-2 border-b border-border py-1.5 text-xs last:border-0">
      <span className="text-fg-subtle">
        <BrasiliaShort iso={position.exit_at} />
      </span>
      <span className="font-mono text-fg">{truncateAddress(position.mint)}</span>
      <span className="font-mono tabular-nums">
        <RValue r={position.r_multiple} />
      </span>
      <span className={`font-mono tabular-nums ${pnlColorClass(position.pnl_sol)}`}>{position.pnl_sol !== null ? formatSolSigned(position.pnl_sol) : "—"}</span>
      <span className="text-fg-muted">{exitReasonLabel(position.exit_reason)}</span>
    </li>
  );
}

function OpenRow({ position, nowMs }: { position: WalletOpenPosition; nowMs: number }) {
  return (
    <li className="flex flex-wrap items-center justify-between gap-2 border-b border-border py-1.5 text-xs last:border-0">
      <span className="text-fg-subtle">
        <BrasiliaShort iso={position.entry_at} />
      </span>
      <span className="font-mono text-fg">{truncateAddress(position.mint)}</span>
      <span className="font-mono tabular-nums text-fg">{position.mark_sol !== null ? formatSol(position.mark_sol) : "sem marca ainda"}</span>
      <span className="text-fg-muted">aberta há {ageSince(position.entry_at, nowMs)}</span>
    </li>
  );
}

export function WalletSummaryLists({ closedToday, open, nowMs }: { closedToday: WalletClosedPosition[]; open: WalletOpenPosition[]; nowMs: number }) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      <div>
        <h3 className="mb-1 text-xs font-semibold uppercase text-fg-muted">Fechadas hoje</h3>
        {closedToday.length === 0 ? (
          <p className="text-sm text-fg-muted">Nenhuma posição fechada hoje.</p>
        ) : (
          <ul>
            {closedToday.map((position) => (
              <ClosedRow key={position.id} position={position} />
            ))}
          </ul>
        )}
      </div>
      <div>
        <h3 className="mb-1 text-xs font-semibold uppercase text-fg-muted">Abertas agora</h3>
        {open.length === 0 ? (
          <p className="text-sm text-fg-muted">Nenhuma posição real aberta agora.</p>
        ) : (
          <ul>
            {open.map((position) => (
              <OpenRow key={position.id} position={position} nowMs={nowMs} />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
