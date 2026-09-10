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

/**
 * Parses a decimal string ("-123.456") into its parts. Throws `TypeError` on anything else.
 *
 * Exponent forms ("0E-20", "1E+2", "1.5e3") are accepted and expanded digit by
 * digit: Python's `str(Decimal)` writes a NUMERIC(…, 20) zero as `0E-20`, and
 * the wallet page crashed server-side on exactly that value (VPS, 2026-09-08).
 * The API now serializes decimals in plain notation, but a reader that only
 * survives one writer's habits is not a reader.
 */
function parseDecimal(raw: string): ParsedDecimal {
  const match = /^([+-])?(\d+)(?:\.(\d+))?(?:[eE]([+-]?\d+))?$/.exec(raw.trim());
  if (!match) {
    throw new TypeError(`Invalid decimal value: ${JSON.stringify(raw)}`);
  }
  const [, signPart, intPart, fracPart, expPart] = match;
  let intDigits = intPart ?? "0";
  let fracDigits = fracPart ?? "";
  if (expPart !== undefined) {
    const exponent = Number.parseInt(expPart, 10);
    const digits = intDigits + fracDigits;
    const point = intDigits.length + exponent;
    if (point <= 0) {
      intDigits = "0";
      fracDigits = "0".repeat(-point) + digits;
    } else if (point >= digits.length) {
      intDigits = digits + "0".repeat(point - digits.length);
      fracDigits = "";
    } else {
      intDigits = digits.slice(0, point);
      fracDigits = digits.slice(point);
    }
  }
  return {
    negative: signPart === "-",
    intDigits: intDigits.replace(/^0+(?=\d)/, ""),
    fracDigits,
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

/** Aligns a parsed decimal's fraction to `fracLength` digits and returns its unsigned magnitude as a `BigInt`. */
function decimalMagnitude(dec: ParsedDecimal, fracLength: number): bigint {
  const frac = dec.fracDigits.padEnd(fracLength, "0");
  return BigInt(`${dec.intDigits || "0"}${frac}`);
}

/**
 * Exact comparison of two `Decimal` strings (string/`BigInt` arithmetic only,
 * same parsing as `formatMoney`/`formatBrl` above) -- for rules where two
 * decimal strings must be compared exactly, `Number(a) >= Number(b)` can
 * flip once either value moves past `2**53`'s exact-integer range, or once
 * two distinct decimal strings round to the same float. Returns -1/0/1 like
 * `Array.prototype.sort`'s comparator contract. Throws `TypeError` (via
 * `parseDecimal`) if either input is not a valid decimal string.
 */
export function compareDecimalStrings(a: string, b: string): number {
  const pa = parseDecimal(a);
  const pb = parseDecimal(b);
  const fracLength = Math.max(pa.fracDigits.length, pb.fracDigits.length);
  const magA = decimalMagnitude(pa, fracLength);
  const magB = decimalMagnitude(pb, fracLength);
  const signedA = pa.negative && magA !== 0n ? -magA : magA;
  const signedB = pb.negative && magB !== 0n ? -magB : magB;
  if (signedA === signedB) return 0;
  return signedA < signedB ? -1 : 1;
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

/**
 * Brazilian Real, styled per the "pt-BR" convention (T3.8b polish pass, first
 * BRL-denominated screen in the product): the integer part is grouped every
 * 3 digits with "." and the fraction is separated with "," -- the opposite
 * of `formatMoney`'s "en-US" grouping. Reusing `formatMoney(value, {currency:
 * "BRL", locale: "en-US"})` (the wallet's original approach) sidesteps a
 * literal collision -- `Intl.NumberFormat("pt-BR")` groups thousands with
 * "." too, so joining the grouped integer and the fraction with a literal
 * "." (as `formatMoney` always does) would print an ambiguous
 * "R$100.000.00" -- but it also means the number never actually reads as
 * Brazilian. This is a sibling implementation instead, built the same
 * decimal-safe way as `formatMoney` (parse into sign/integer/fraction parts,
 * round with `BigInt` arithmetic via `roundDecimal`, group with
 * `Intl.NumberFormat`'s `bigint` support via `groupInteger`) but joining the
 * pieces with "," for the fraction, so it is `formatMoney` itself -- and
 * every other USD/en-US caller in the product -- that stays untouched.
 *
 * Rounding is half-up on the third fraction digit, the same convention
 * `roundDecimal` already applies for every other currency in the product
 * (verified: `"99999.99999999983784"` rounds to `"100000.00"`, i.e. the
 * carry propagates through every "9"). A second rounding rule for one
 * currency would be its own kind of surprise, so this deliberately does not
 * introduce half-even.
 *
 * Never routes the value through `Number()`: like `formatMoney`, a
 * `Decimal` string beyond `2**53` keeps every digit, because the sign/int/
 * frac split and the rounding both work on strings/`BigInt`, not floats.
 *
 * Negative amounts use the Unicode minus sign "−" (U+2212) *before* "R$"
 * (e.g. "−R$ 1.234,56"), not the ASCII hyphen-minus -- the typographic sign
 * `Intl`'s own pt-BR currency data reaches for, and the placement a
 * Brazilian-first reading expects at a glance.
 */
export function formatBrl(value: string | number): string {
  const rounded = roundDecimal(parseDecimal(normalizeToDecimalString(value)), 2);
  const groupedInt = groupInteger(rounded.intDigits, "pt-BR");
  const { prefix } = currencyParts("pt-BR", "BRL");
  // Node/ICU renders the pt-BR currency prefix with U+00A0 (non-breaking
  // space) between "R$" and the number -- normalized here to a plain
  // U+0020 space so the rendered text matches what the rest of the UI (and
  // every test asserting on it) can select and compare as an ordinary
  // string.
  const normalizedPrefix = prefix.replace(new RegExp(String.fromCharCode(160), "g"), " ");
  const sign = rounded.negative ? "−" : "";
  return `${sign}${normalizedPrefix}${groupedInt},${rounded.fracDigits}`;
}

/** `formatBrl` with an explicit leading "+" on a non-zero, non-negative amount (docs/DESIGN.md §2: signed numbers) -- mirrors `formatUsdtSigned` below; `formatBrl` already prints "−" for negatives but never "+" for positives. */
export function formatBrlSigned(value: string | number): string {
  const raw = typeof value === "number" ? value.toString() : value;
  const isZero = /^[+-]?0+(\.0+)?$/.test(raw.trim());
  const negative = raw.trim().startsWith("-");
  const sign = isZero || negative ? "" : "+";
  return `${sign}${formatBrl(value)}`;
}

/**
 * USDT has no ISO 4217 code, so `formatMoney`'s Intl currency style cannot
 * render it (`Intl.NumberFormat` throws `RangeError` for an unknown currency).
 * Reuses `formatMoney`'s decimal-safe grouping/rounding under "USD" (same
 * digit grouping, en-US locale) and swaps the "$" for an explicit "USDT"
 * suffix -- the wallet's operating currency (M3, ADR 0005) must never read as
 * US dollars just because it shares USD's digit formatting.
 */
export function formatUsdt(value: string | number, decimals = 2): string {
  const bare = formatMoney(value, { currency: "USD", decimals }).replace(/[^0-9.,-]/g, "");
  return `${bare} USDT`;
}

/** `formatUsdt` with an explicit leading "+" on a non-zero, non-negative amount (docs/DESIGN.md §2: signed numbers), e.g. for PnL/decomposition lines where "10.00 USDT" and "-10.00 USDT" alone would not visually separate gain from loss. */
export function formatUsdtSigned(value: string | number, decimals = 2): string {
  const raw = typeof value === "number" ? value.toString() : value;
  const isZero = /^[+-]?0+(\.0+)?$/.test(raw.trim());
  const negative = raw.trim().startsWith("-");
  const sign = isZero || negative ? "" : "+";
  return `${sign}${formatUsdt(value, decimals)}`;
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
 * browser, any timezone. Brief T3.22 (2026-09-08, Everton: "sou de sao
 * paulo intao horario tem que ser de brasilia") moved every screen's PRIMARY
 * timestamp to Brasília (`lib/time.ts`'s `formatBrasiliaShort`/
 * `formatBrasiliaLong`); this function now backs the secondary UTC half --
 * a `title`/tooltip, or the System page's operator detail -- never the
 * first thing a viewer reads. Still deterministic in any runtime timezone
 * (server container or browser), so it stays safe to call during SSR.
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
