import { Badge } from "@/components/ui/badge";
import type { SpotMarketOption } from "@/lib/api/markets-actions";
import { formatCompact, formatUsdt } from "@/lib/format";

/** `min_liquidity_usd_24h` (docs/RISK_ENGINE.md §2, paper_v1) -- see `manual-order-market-field.tsx`'s own docstring for why this is informational, never the admission source of truth. */
const SPOT_FLOOR_USDT = 50_000_000;

export function floorMet(volume24h: string | null): boolean | null {
  if (volume24h === null) return null;
  const value = Number(volume24h);
  return Number.isFinite(value) ? value >= SPOT_FLOOR_USDT : null;
}

export interface ManualOrderMarketChipProps {
  market: SpotMarketOption;
  onClear: () => void;
  disabled: boolean;
}

/** The selected-market summary chip (extracted out of `manual-order-market-field.tsx` to keep it under the lint config's per-function complexity budget). */
export function ManualOrderMarketChip({ market, onClear, disabled }: ManualOrderMarketChipProps) {
  const met = floorMet(market.volume_24h);
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-md border border-border-input bg-bg px-2 py-1.5">
      <span className="font-mono text-sm text-fg">{market.symbol}</span>
      <span className="text-xs text-fg-muted">{market.exchange}</span>
      <span className="font-mono text-xs tabular-nums text-fg-muted">
        {market.volume_24h !== null ? `${formatCompact(market.volume_24h)} ${market.quote_asset ?? ""}`.trim() : "volume indisponível"}
      </span>
      {met !== null && <Badge variant={met ? "positive" : "warning"}>{met ? "Acima do piso (50M)" : "Abaixo do piso (banda de saída)"}</Badge>}
      {market.last_price !== null && <span className="font-mono text-xs tabular-nums text-fg-muted">último: {formatUsdt(market.last_price)}</span>}
      <button
        type="button"
        onClick={onClear}
        disabled={disabled}
        className="ml-auto rounded-sm text-xs text-fg-muted underline decoration-dotted underline-offset-2 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold disabled:opacity-50"
      >
        Trocar
      </button>
    </div>
  );
}
