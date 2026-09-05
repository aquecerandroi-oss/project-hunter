"use client";

import { useEffect, useState } from "react";

import { formatLocalOffset, formatUtc } from "@/lib/format";
import type { RecentTrade } from "@/lib/api/types";
import { cn } from "@/lib/utils";

export interface RecentTradesProps {
  /** `null` (`MarketDetailOut.recent_trades`, H3) means the Redis hot-state read itself failed -- a real, empty `[]` means the read succeeded and there is genuinely nothing recent. */
  trades: RecentTrade[] | null;
  /** `MarketDetailOut.hot_state_ok` -- the explicit signal behind a `null` `trades`, checked first so the failure message never depends solely on `trades === null` holding true by convention. */
  hotStateOk: boolean;
}

const SIDE_LABEL: Record<"buy" | "sell", string> = { buy: "Compra", sell: "Venda" };
const SIDE_GLYPH: Record<"buy" | "sell", string> = { buy: "C", sell: "V" };

/**
 * The local offset is a client-only enhancement (H2, T1.5b fix pass): the
 * server (often a UTC container) and the browser (often not) can compute a
 * different local time from the exact same ISO timestamp, so it must never
 * appear in the SSR'd markup -- only `formatUtc` (deterministic everywhere)
 * is safe there. `null` until the effect below runs once after mount; one
 * extra client-only render adds the offset, never a server/client mismatch.
 */
function useTradeTimestampText(iso: string): string {
  const [local, setLocal] = useState<string | null>(null);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- syncing from the runtime's own timezone, an external system, once mounted (H2)
    setLocal(formatLocalOffset(iso));
  }, [iso]);

  const utc = formatUtc(iso);
  return local ? `${utc} (${local})` : utc;
}

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
        <TradeItem key={trade.trade_id} trade={trade} />
      ))}
    </ul>
  );
}

function TradeItem({ trade }: { trade: RecentTrade }) {
  // Hooks can't be called from inside `.map`'s callback directly -- this
  // small subcomponent is what lets each row own its own client-only local
  // offset without breaking the rules of hooks.
  const timestampText = useTradeTimestampText(trade.ts);

  return (
    // Buy/sell distinguished by more than color alone (docs/DESIGN.md's
    // semantic-color rule, applied the same way `QualityBadge` and
    // signed percentages already do) -- a colourblind or screen-reader
    // user gets the glyph/aria-label, not just green/red (T1.5 review F8).
    <li
      // `flex-col` on narrow widths (the UTC+offset timestamp is long
      // and unshrinkable) and `sm:flex-row` once there's room -- T1.5b
      // Astra must-fix #7: this used to force everything onto one
      // non-wrapping line, squeezing price/qty against the timestamp.
      className="flex flex-col gap-x-2 gap-y-0.5 px-2 py-1 font-mono tabular-nums sm:flex-row sm:items-center sm:justify-between sm:py-0.5"
      aria-label={`${SIDE_LABEL[trade.side]} de ${trade.qty} a ${trade.price}, ${timestampText}`}
    >
      {/*
       * Time is always UTC (CLAUDE.md) with the local offset shown next
       * to it in visible text -- never only in a `title` attribute,
       * which a touch or screen-reader user can't reach (T1.5b joint
       * decision #9: "horários acessíveis sem hover"). UTC renders
       * immediately (server-safe, H2); the local offset appears a moment
       * later, once mounted client-side.
       */}
      <span className="text-[11px] text-fg-subtle sm:shrink-0">{timestampText}</span>
      <span className="flex items-center justify-between gap-2 sm:contents">
        <span className={cn("flex items-center gap-1", trade.side === "buy" ? "text-green" : "text-red")}>
          <span aria-hidden="true" className="text-[10px] font-semibold uppercase">
            {SIDE_GLYPH[trade.side]}
          </span>
          {trade.price}
        </span>
        <span className="text-fg-muted">{trade.qty}</span>
      </span>
    </li>
  );
}
