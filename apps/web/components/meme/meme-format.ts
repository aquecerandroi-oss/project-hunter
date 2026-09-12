/**
 * Meme Radar-specific number formatting. SOL has no ISO 4217 code (same
 * problem `lib/format.ts`'s `formatUsdt` solves for USDT): reuses
 * `formatMoney`'s decimal-safe grouping/rounding under "USD" and swaps the
 * suffix, so a 28-digit reserve never loses precision through `Number()`.
 */
import { formatMoney, formatPct } from "@/lib/format";

export function formatSol(value: string, decimals = 4): string {
  const bare = formatMoney(value, { currency: "USD", decimals }).replace(/[^0-9.,-]/g, "");
  return `${bare} SOL`;
}

/** Curve progress / minute coverage / top10 share are all 0..1 fractions (contract: `numeric(9,6)`) -- never signed (there is no "negative progress"). */
export function formatMemePct(value: string, digits = 2): string {
  return formatPct(value, { signed: false, digits });
}

/** `buy_sell_ratio` is a plain ratio (buys/sells by count), not a percentage or a currency -- two decimals, no unit. */
export function formatRatio(value: string): string {
  const n = Number(value);
  return Number.isFinite(n) ? n.toFixed(2) : value;
}
