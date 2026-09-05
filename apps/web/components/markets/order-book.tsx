import type { MarketBook, OrderBookLevel } from "@/lib/api/types";
import { cn } from "@/lib/utils";

export interface OrderBookProps {
  book: MarketBook | null;
  /**
   * `MarketDetailOut.hot_state_ok` (H3) -- `false` means the Redis read
   * itself failed, so `book` is `null` because the API *could not ask*, not
   * because there is genuinely no book. Rendering "Book indisponível" for
   * both cases told the user "there is nothing" for what was actually a
   * failed read (e.g. Redis down).
   */
  hotStateOk: boolean;
}

interface Level {
  price: string;
  qty: string;
  cumulative: number;
}

function withCumulative(levels: OrderBookLevel[]): Level[] {
  let running = 0;
  return levels.map(({ price, qty }) => {
    running += Number(qty);
    return { price, qty, cumulative: running };
  });
}

function BookSide({ title, levels, maxCumulative, barColor, priceColor }: { title: string; levels: Level[]; maxCumulative: number; barColor: string; priceColor: string }) {
  return (
    <div>
      <h3 className="mb-1 text-[11px] font-medium uppercase tracking-wide text-fg-muted">{title}</h3>
      <ul className="flex flex-col gap-px">
        {levels.map((level) => (
          <li key={level.price} className="relative flex justify-between px-2 py-0.5 font-mono tabular-nums">
            <div
              className={cn("absolute inset-y-0 right-0", barColor)}
              style={{ width: `${Math.min(100, (level.cumulative / maxCumulative) * 100)}%` }}
              aria-hidden="true"
            />
            <span className={cn("relative", priceColor)}>{level.price}</span>
            <span className="relative text-fg-muted">{level.qty}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Top-20 book, two columns with cumulative-quantity depth bars (docs/plans/M1.md
 * T1.5). `book.depth` is always 20 (T1.4's projection). Rendered in the order
 * the API sends each side -- exchange convention (and Binance's own `@depth20`
 * stream, per docs/EXCHANGE_INTEGRATION.md §1) is bids best-to-worst
 * (descending price) and asks best-to-worst (ascending price).
 */
export function OrderBook({ book, hotStateOk }: OrderBookProps) {
  if (!hotStateOk) {
    return <p className="text-sm text-fg-muted">Book indisponível: falha ao ler o estado em tempo real (Redis).</p>;
  }

  if (!book) {
    return <p className="text-sm text-fg-muted">Book indisponível.</p>;
  }

  const bids = withCumulative(book.bids);
  const asks = withCumulative(book.asks);
  const maxCumulative = Math.max(bids.at(-1)?.cumulative ?? 0, asks.at(-1)?.cumulative ?? 0, 1);

  return (
    <div className="grid grid-cols-2 gap-3 text-xs">
      <BookSide title="Bids" levels={bids} maxCumulative={maxCumulative} barColor="bg-green/10" priceColor="text-green" />
      <BookSide title="Asks" levels={asks} maxCumulative={maxCumulative} barColor="bg-red/10" priceColor="text-red" />
    </div>
  );
}
