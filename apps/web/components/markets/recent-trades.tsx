import { formatBrasiliaLong } from "@/lib/time";
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
  // Brief T3.22 (2026-09-08): primary text is Brasília, deterministic in any
  // runtime timezone (`lib/time.ts`'s explicit `timeZone` option) -- no
  // client-only effect needed anymore, unlike the previous UTC +
  // browser-local-offset version (H2 no longer applies once the display
  // timezone is fixed rather than the browser's own).
  const timestampText = formatBrasiliaLong(trade.ts) ?? "--";

  return (
    // Buy/sell distinguished by more than color alone (docs/DESIGN.md's
    // semantic-color rule, applied the same way `QualityBadge` and
    // signed percentages already do) -- a colourblind or screen-reader
    // user gets the glyph/aria-label, not just green/red (T1.5 review F8).
    <li
      // `flex-col` on narrow widths (the timestamp is long and
      // unshrinkable) and `sm:flex-row` once there's room -- T1.5b Astra
      // must-fix #7: this used to force everything onto one non-wrapping
      // line, squeezing price/qty against the timestamp.
      className="flex flex-col gap-x-2 gap-y-0.5 px-2 py-1 font-mono tabular-nums sm:flex-row sm:items-center sm:justify-between sm:py-0.5"
      aria-label={`${SIDE_LABEL[trade.side]} de ${trade.qty} a ${trade.price}, ${timestampText}`}
    >
      {/*
       * Brasília, the organization's one display timezone (brief T3.22),
       * shown in visible text -- never only in a `title` attribute, which a
       * touch or screen-reader user can't reach (T1.5b joint decision #9:
       * "horários acessíveis sem hover"). The exact UTC instant stays one
       * hover away in `title`: the raw ISO string is already UTC and
       * copyable as-is.
       */}
      <span title={trade.ts} className="text-[11px] text-fg-subtle sm:shrink-0">
        {timestampText}
      </span>
      <span className="flex items-center justify-between gap-2 sm:contents">
        <span className={cn("flex items-center gap-1", trade.side === "buy" ? "text-green" : "text-red")}>
          <span aria-hidden="true" className="text-[11px] font-semibold uppercase">
            {SIDE_GLYPH[trade.side]}
          </span>
          {trade.price}
        </span>
        <span className="text-fg-muted">{trade.qty}</span>
      </span>
    </li>
  );
}
