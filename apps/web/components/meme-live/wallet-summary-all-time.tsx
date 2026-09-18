/**
 * "Carteira real" §3 "Desde o início" (T4.57): every field a plain aggregate
 * over `meme_live_positions`, and the wallet's starting equity, labelled by
 * whichever reading the database actually kept (never an invented "day 1").
 */
import { formatSol } from "@/components/meme/meme-format";
import { BrasiliaShort } from "@/components/time/brasilia-instant";

import type { WalletAllTime, WalletBestWorst } from "@/lib/api/meme-live-wallet-types";
import { truncateAddress } from "./live-format";
import { formatSolSigned, pnlColorClass, startingEquitySourceLabel, walletReasonLabel } from "./wallet-summary-format";

function BestWorst({ label, trade, reason }: { label: string; trade: WalletBestWorst | null; reason: string | null }) {
  return (
    <div>
      <p className="text-[11px] font-medium uppercase text-fg-muted">{label}</p>
      {trade ? (
        <p className={`font-mono text-sm tabular-nums ${pnlColorClass(trade.pnl_sol)}`}>
          {formatSolSigned(trade.pnl_sol)} <span className="text-fg-subtle">{truncateAddress(trade.mint)}</span>
        </p>
      ) : (
        <p className="text-sm text-fg-muted">{walletReasonLabel(reason)}</p>
      )}
    </div>
  );
}

export function WalletSummaryAllTime({ allTime }: { allTime: WalletAllTime }) {
  const totalPnl = allTime.total_pnl_sol !== null ? formatSolSigned(allTime.total_pnl_sol) : walletReasonLabel(allTime.total_pnl_sol_reason);
  const startingSource = startingEquitySourceLabel(allTime.starting_equity_source);

  return (
    <div className="flex flex-col gap-3">
      <h3 className="text-xs font-semibold uppercase text-fg-muted">Desde o início</h3>
      <p className="text-xs text-fg-muted">
        compras <span className="font-mono tabular-nums text-fg">{allTime.total_bought}</span> · ganhas{" "}
        <span className="font-mono tabular-nums text-green">{allTime.total_won}</span> · perdidas{" "}
        <span className="font-mono tabular-nums text-red">{allTime.total_lost}</span>
      </p>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div>
          <p className="text-[11px] font-medium uppercase text-fg-muted">PnL acumulado</p>
          <p className={`font-mono text-base tabular-nums ${pnlColorClass(allTime.total_pnl_sol)}`}>{totalPnl}</p>
        </div>
        <BestWorst label="Maior ganho" trade={allTime.best_trade} reason="no_closed_positions" />
        <BestWorst label="Maior perda" trade={allTime.worst_trade} reason="no_closed_positions" />
        <div>
          <p className="text-[11px] font-medium uppercase text-fg-muted">Equity inicial</p>
          {allTime.starting_equity_sol !== null ? (
            <>
              <p className="font-mono text-base tabular-nums text-fg">{formatSol(allTime.starting_equity_sol)}</p>
              <p className="text-[11px] text-fg-subtle">
                {startingSource}
                {allTime.starting_equity_at && (
                  <>
                    {" "}
                    em <BrasiliaShort iso={allTime.starting_equity_at} />
                  </>
                )}
              </p>
            </>
          ) : (
            <p className="text-sm text-fg-muted">{walletReasonLabel(allTime.starting_equity_reason)}</p>
          )}
        </div>
      </div>
    </div>
  );
}
