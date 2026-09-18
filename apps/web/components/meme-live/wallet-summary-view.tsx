/**
 * "Carteira real" (T4.57, Everton 18/09/2026): the panel at the top of
 * `/meme/mesa` answering "quanto tenho, o que ganhei/perdi hoje, e desde o
 * início" at a glance. Presentational only -- `wallet-summary-panel.tsx`
 * owns the 10 s poll (`useWalletSummaryPoll`) and passes the latest
 * `WalletSummary` (or `null` before the first response) down here, so this
 * component is testable with plain props (no timers, no fetch mock needed).
 */
import { RealBadge } from "./real-confirm";
import { WalletSummaryAllTime } from "./wallet-summary-all-time";
import { walletExecutorStatusNote } from "./wallet-summary-format";
import { WalletSummaryLists } from "./wallet-summary-lists";
import { WalletSummaryNow } from "./wallet-summary-now";
import { WalletSummaryToday } from "./wallet-summary-today";

import type { WalletSummary } from "@/lib/api/meme-live-wallet-types";

export interface WalletSummaryViewProps {
  summary: WalletSummary | null;
  /** A poll failure's message -- shown alongside stale data when `summary` is not `null`, or as the whole panel's honest state when it is. */
  reason: string | null;
}

function Header({ status }: { status: string | null }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <RealBadge />
      <h2 className="text-sm font-semibold text-fg">Carteira real</h2>
      {status && <span className="text-xs text-fg-muted">{walletExecutorStatusNote(status)}</span>}
    </div>
  );
}

export function WalletSummaryView({ summary, reason }: WalletSummaryViewProps) {
  if (!summary) {
    return (
      <section className="flex flex-col gap-2 rounded-lg border border-red/30 bg-bg-elevated p-4">
        <Header status={null} />
        <p className="text-sm text-fg-muted">{reason ? `Carteira indisponível: ${reason}` : "Carregando a carteira real..."}</p>
      </section>
    );
  }

  const nowMs = new Date(summary.server_now).getTime();

  return (
    <section className="flex flex-col gap-4 rounded-lg border border-red/30 bg-bg-elevated p-4">
      <Header status={summary.executor_status} />
      {reason && <p className="text-[11px] font-medium text-warning">Falha na última atualização — mostrando a última leitura boa: {reason}</p>}
      <WalletSummaryNow now={summary.now} />
      <WalletSummaryToday today={summary.today} />
      <WalletSummaryAllTime allTime={summary.all_time} />
      <WalletSummaryLists closedToday={summary.closed_today} open={summary.open} nowMs={nowMs} />
    </section>
  );
}
