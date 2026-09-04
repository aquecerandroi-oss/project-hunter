/**
 * Number formatting for the UI layer only. Inputs are typed as
 * `string | number` because the API sends money/quantity fields as decimal
 * strings (backend truth is `Decimal` / `NUMERIC(28,10)`, never `float` --
 * see CLAUDE.md). Converting to `Number` here is a *display* concern: at
 * M0 UI values are not used for any calculation, only rendering, so the
 * float precision loss this implies is acceptable for formatting and never
 * propagates back into a request body.
 */

function toNumber(value: string | number): number {
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : 0;
}

export function formatMoney(value: string | number, currency = "USD", locale = "en-US"): string {
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(toNumber(value));
}

export function formatPct(value: string | number, opts: { signed?: boolean; digits?: number } = {}): string {
  const { signed = true, digits = 2 } = opts;
  return new Intl.NumberFormat("en-US", {
    style: "percent",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
    signDisplay: signed ? "exceptZero" : "auto",
    // formatPct expects a fraction already scaled to 0-1 (e.g. 0.023 for
    // 2.30%), matching how the API expresses percentages.
  }).format(toNumber(value));
}

export function formatCompact(value: string | number, locale = "en-US"): string {
  return new Intl.NumberFormat(locale, {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(toNumber(value));
}
