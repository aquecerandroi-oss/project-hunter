import { formatPrice } from "@/components/markets/format";
import { WhenCell } from "@/components/lab/lab-when-cell";

export interface LabPriceTimeCellProps {
  price: string | null;
  ts: string | null;
}

/**
 * "Entrou"/"Saiu" price+time, two lines max (brief T3.17b item 3: "price and
 * time on one line each"). Price is the primary fact -- top line, full
 * contrast, `docs/DESIGN.md` §2's "price with the most contrast of the row";
 * the instant is secondary -- bottom line, muted, no "UTC" suffix.
 */
export function LabPriceTimeCell({ price, ts }: LabPriceTimeCellProps) {
  if (price === null) return <span className="text-fg-muted">--</span>;
  return (
    <span className="flex flex-col items-end leading-tight">
      <span className="font-mono tabular-nums text-fg">{formatPrice(price)}</span>
      <WhenCell iso={ts} suffix={false} className="font-mono text-[11px] tabular-nums text-fg-muted" />
    </span>
  );
}
