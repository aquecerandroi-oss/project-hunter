import { formatCompact, formatPct } from "@/lib/format";

/**
 * Market-specific number formatting. Prices/quantities stay as the raw
 * `Decimal` string the API sent -- CLAUDE.md's "money is Decimal, never
 * float" extends to display: reformatting a high-precision altcoin price
 * through `Number` would silently lose digits. Only volumes (safely
 * compact-able magnitudes) and percentages route through `lib/format.ts`.
 *
 * Percentage fields are NOT all scaled the same way -- read the field's own
 * doc comment before adding a new one:
 *   - `price_change_24h_pct` arrives already scaled to percent (Binance's
 *     `priceChangePercent`, e.g. "1.23" means 1.23%) -- see
 *     `formatSignedPercentNumber`, which only adds the sign/suffix.
 *   - `spread_pct` and `funding_rate` arrive as fractions (e.g. "0.02" means
 *     2%, matching `docs/DATABASE.md` §1's percentage-as-fraction
 *     convention) -- both route through `lib/format.ts`'s `formatPct`,
 *     which multiplies by 100 for display.
 */

// `MarketOut`/`MarketDetailOut`'s fields are generated as `string | null`
// *and* optional (Pydantic default => OpenAPI `?`) even though the API
// always serializes them -- these accept `undefined` too so a generated
// alias can be passed straight through without a defensive `?? null` at
// every call site (H1).
export function formatPrice(value: string | null | undefined): string {
  return value ?? "--";
}

/** `price_change_24h_pct` arrives already scaled to percent (Binance convention), so this only adds the sign/suffix. */
export function formatSignedPercentNumber(value: string | null | undefined): string {
  if (value === null || value === undefined) return "--";
  return value.trim().startsWith("-") ? `${value}%` : `+${value}%`;
}

/** `spread_pct` is a fraction (e.g. `0.02` = 2%), like `funding_rate` below -- unsigned, since a spread is never negative. */
export function formatSpread(value: string | null | undefined): string {
  return value === null || value === undefined ? "--" : formatPct(value, { digits: 3, signed: false });
}

export function formatVolume(value: string | null | undefined): string {
  return value === null || value === undefined ? "--" : formatCompact(value);
}

/** `funding_rate` is a fraction (e.g. `0.0001` = 0.01%), unlike `price_change_24h_pct`. */
export function formatFundingRate(value: string | null | undefined): string {
  return value === null || value === undefined ? "--" : formatPct(value, { digits: 4 });
}
