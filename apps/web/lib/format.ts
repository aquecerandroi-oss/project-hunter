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

/**
 * Time is always UTC (CLAUDE.md) -- deterministic everywhere, server or
 * browser, any timezone. This is the ONLY half of a timestamp that is safe
 * to render during SSR (H2, T1.5b fix pass): `formatUtcWithOffset` below
 * used to call `date.getTimezoneOffset()` (the *runtime's* zone) directly in
 * render, so a UTC-container server and a non-UTC browser produced different
 * text for the exact same trade -- a hydration mismatch on every trade row
 * for every non-UTC user. Callers that render during SSR (e.g.
 * `components/markets/recent-trades.tsx`) must use this function for the
 * first paint and add the local offset only as a client-only enhancement
 * after mount (see that component's `useLocalOffsetSuffix`).
 */
export function formatUtc(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "--";

  const utc = new Intl.DateTimeFormat("en-GB", {
    timeZone: "UTC",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(date);

  return `${utc} UTC`;
}

/**
 * The local wall-clock time with its signed UTC offset, e.g. `"11:32:10
 * -03:00"` -- deliberately NOT part of `formatUtc` above, since it depends
 * on the runtime's own timezone (`Intl.DateTimeFormat`'s implicit zone /
 * `Date#getTimezoneOffset`) and must only ever be computed client-side,
 * after mount (H2). Returns `null` for an invalid timestamp so a caller can
 * fall back to just the UTC part without a "--" leaking into the offset.
 */
export function formatLocalOffset(iso: string): string | null {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;

  const local = new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(date);

  // `getTimezoneOffset()` is minutes to ADD to local time to reach UTC (so
  // it's the negative of the conventional "+02:00" style offset) -- flip the
  // sign here rather than at every call site.
  const offsetMinutes = -date.getTimezoneOffset();
  const sign = offsetMinutes >= 0 ? "+" : "-";
  const abs = Math.abs(offsetMinutes);
  const offsetHours = String(Math.floor(abs / 60)).padStart(2, "0");
  const offsetRemainder = String(abs % 60).padStart(2, "0");

  return `${local} ${sign}${offsetHours}:${offsetRemainder}`;
}

/**
 * UTC clock + local offset in one string, e.g. `"14:32:10 UTC (11:32:10
 * -03:00)"` (joint decision #9: "horários acessíveis sem hover... em UTC com
 * offset local"). Safe to call anywhere that does NOT render during SSR --
 * see `formatUtc`'s docstring for the one place (SSR'd trade rows) that
 * needs the two halves split apart instead.
 */
export function formatUtcWithOffset(iso: string): string {
  const utc = formatUtc(iso);
  if (utc === "--") return "--";
  const local = formatLocalOffset(iso);
  return local ? `${utc} (${local})` : utc;
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
