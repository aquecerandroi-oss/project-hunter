import type { RecentTrade } from "@/lib/api/types";
import { cn } from "@/lib/utils";

export interface RecentTradesProps {
  /** `null` (`MarketDetailOut.recent_trades`, H3) means the Redis hot-state read itself failed -- a real, empty `[]` means the read succeeded and there is genuinely nothing recent. */
  trades: RecentTrade[] | null;
  /** `MarketDetailOut.hot_state_ok` -- the explicit signal behind a `null` `trades`, checked first so the failure message never depends solely on `trades === null` holding true by convention. */
  hotStateOk: boolean;
}

function formatTime(iso: string): string {
  return new Intl.DateTimeFormat("pt-BR", { timeStyle: "medium" }).format(new Date(iso));
}

const SIDE_LABEL: Record<"buy" | "sell", string> = { buy: "Compra", sell: "Venda" };
const SIDE_GLYPH: Record<"buy" | "sell", string> = { buy: "C", sell: "V" };

/** Most recent trade first (docs/plans/M1.md T1.5). Honest empty state when there is nothing yet, never a placeholder row -- and a distinct honest failure state (H3) when the read itself failed, never mistaken for "nothing yet". */
export function RecentTrades({ trades, hotStateOk }: RecentTradesProps) {
  if (!hotStateOk || trades === null) {
    return <p className="text-sm text-fg-muted">Trades indisponíveis: falha ao ler o estado em tempo real (Redis).</p>;
  }

  if (trades.length === 0) {
    return <p className="text-sm text-fg-muted">Nenhum trade recente.</p>;
  }

  return (
    <ul className="flex flex-col gap-px text-xs">
      {trades.map((trade) => (
        // Buy/sell distinguished by more than color alone (docs/DESIGN.md's
        // semantic-color rule, applied the same way `QualityBadge` and
        // signed percentages already do) -- a colourblind or screen-reader
        // user gets the glyph/aria-label, not just green/red (T1.5 review F8).
        <li
          key={trade.trade_id}
          className="flex justify-between px-2 py-0.5 font-mono tabular-nums"
          aria-label={`${SIDE_LABEL[trade.side]} de ${trade.qty} a ${trade.price}`}
        >
          <span className="text-fg-subtle">{formatTime(trade.ts)}</span>
          <span className={cn("flex items-center gap-1", trade.side === "buy" ? "text-green" : "text-red")}>
            <span aria-hidden="true" className="text-[10px] font-semibold uppercase">
              {SIDE_GLYPH[trade.side]}
            </span>
            {trade.price}
          </span>
          <span className="text-fg-muted">{trade.qty}</span>
        </li>
      ))}
    </ul>
  );
}
