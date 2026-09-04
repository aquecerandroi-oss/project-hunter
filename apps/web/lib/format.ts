/**
 * Number formatting for the UI layer only. Inputs are typed as
 * `string | number` because the API sends money/quantity fields as decimal
 * strings (backend truth is `Decimal` / `NUMERIC(28,10)`, never `float` --
 * see CLAUDE.md).
 *
 * `formatMoney` never routes the full value through `Number()`: a
 * `Decimal` string like a 28-digit balance would silently lose precision
 * the moment it becomes an IEEE-754 double. Instead we parse the string
 * into sign/integer/fraction parts, round with `BigInt` arithmetic, and
 * group digits with `Intl.NumberFormat`'s `bigint` support. Only
 * `formatCompact` still uses `Number`, and only for magnitudes that fit a
 * float exactly (<= 2^53); above that it falls back to the same
 * decimal-safe path as `formatMoney`.
 */

interface ParsedDecimal {
  negative: boolean;
  intDigits: string;
  fracDigits: string;
}

/** Converts a finite number to a plain (non-exponential) decimal string. */
function numberToPlainString(n: number): string {
  if (Number.isInteger(n) && Math.abs(n) < 1e21) return n.toString();
  if (Math.abs(n) >= 1e-6 && Math.abs(n) < 1e21) return n.toString();
  // Outside the range where Number#toString stays non-exponential.
  return n.toFixed(20).replace(/0+$/, "").replace(/\.$/, "");
}

function normalizeToDecimalString(value: string | number): string {
  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      throw new TypeError(`Expected a finite number, got ${value}`);
    }
    return numberToPlainString(value);
  }
  return value;
}

/** Parses a plain decimal string ("-123.456") into its parts. Throws `TypeError` on anything else. */
function parseDecimal(raw: string): ParsedDecimal {
  const match = /^([+-])?(\d+)(?:\.(\d+))?$/.exec(raw.trim());
  if (!match) {
    throw new TypeError(`Invalid decimal value: ${JSON.stringify(raw)}`);
  }
  const [, signPart, intPart, fracPart] = match;
  return {
    negative: signPart === "-",
    intDigits: (intPart ?? "0").replace(/^0+(?=\d)/, ""),
    fracDigits: fracPart ?? "",
  };
}

/** Rounds half-up to `decimals` fraction digits using string/BigInt arithmetic (no float involved). */
function roundDecimal(dec: ParsedDecimal, decimals: number): ParsedDecimal {
  const fracPadded = dec.fracDigits.padEnd(decimals + 1, "0");
  const kept = fracPadded.slice(0, decimals);
  const roundUpDigit = fracPadded.charCodeAt(decimals) - 48;

  let combined = `${dec.intDigits}${kept}`;
  if (roundUpDigit >= 5) {
    combined = (BigInt(combined) + 1n).toString();
  }
  const splitAt = combined.length - decimals;
  return {
    negative: dec.negative,
    intDigits: combined.slice(0, splitAt) || "0",
    fracDigits: combined.slice(splitAt),
  };
}

/** Locale-groups an all-digit integer string via `Intl.NumberFormat`'s `bigint` support. */
function groupInteger(digits: string, locale: string): string {
  return new Intl.NumberFormat(locale).format(BigInt(digits || "0"));
}

/** Splits a currency's Intl formatting into the parts surrounding the number itself. */
function currencyParts(locale: string, currency: string): { prefix: string; suffix: string } {
  const parts = new Intl.NumberFormat(locale, {
    style: "currency",
    currency,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).formatToParts(0);

  let prefix = "";
  let suffix = "";
  let pastNumber = false;
  for (const part of parts) {
    if (part.type === "integer" || part.type === "group" || part.type === "decimal" || part.type === "fraction") {
      pastNumber = true;
      continue;
    }
    if (pastNumber) suffix += part.value;
    else prefix += part.value;
  }
  return { prefix, suffix };
}

export interface FormatMoneyOptions {
  currency?: string;
  locale?: string;
  /** Fraction digits to round and display. Default 2. */
  decimals?: number;
}

export function formatMoney(value: string | number, opts: FormatMoneyOptions = {}): string {
  const { currency = "USD", locale = "en-US", decimals = 2 } = opts;
  const rounded = roundDecimal(parseDecimal(normalizeToDecimalString(value)), decimals);
  const groupedInt = groupInteger(rounded.intDigits, locale);
  const numberStr = decimals > 0 ? `${groupedInt}.${rounded.fracDigits}` : groupedInt;
  const { prefix, suffix } = currencyParts(locale, currency);
  const sign = rounded.negative ? "-" : "";
  return `${sign}${prefix}${numberStr}${suffix}`;
}

function toNumber(value: string | number): number {
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : 0;
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
  const raw = normalizeToDecimalString(value);
  const approx = Number(raw);
  if (!Number.isFinite(approx)) {
    throw new TypeError(`Invalid decimal value: ${JSON.stringify(raw)}`);
  }

  if (Math.abs(approx) <= Number.MAX_SAFE_INTEGER) {
    return new Intl.NumberFormat(locale, { notation: "compact", maximumFractionDigits: 1 }).format(approx);
  }

  // Beyond safe-integer magnitude: fall back to the decimal-safe (non-compact) path.
  const rounded = roundDecimal(parseDecimal(raw), 2);
  const groupedInt = groupInteger(rounded.intDigits, locale);
  const sign = rounded.negative ? "-" : "";
  return `${sign}${groupedInt}.${rounded.fracDigits}`;
}
