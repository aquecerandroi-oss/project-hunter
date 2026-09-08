/**
 * The organization's single display timezone (brief T3.22, Everton
 * 2026-09-08 verbatim: "o horario ta errado sou de sao paulo intao horario
 * tem que ser de brasilia"). Every PRIMARY timestamp on screen renders in
 * Brasília time -- never the viewer's own browser timezone, so a member
 * reading the dashboard from abroad still sees the wallet's own day. UTC
 * stays the storage/API truth (CLAUDE.md: "Time is always UTC") and moves to
 * the tooltip/`title` plus the raw ISO string, which is already UTC and
 * copyable as-is.
 *
 * Brazil has observed no DST since 2019 (Decreto 9.772/2019 discontinued the
 * last DST cycle that year), so `America/Sao_Paulo` is a flat UTC-03:00
 * year-round today -- this file still asks `Intl` to resolve the offset live
 * instead of hardcoding "-03:00", so a future legal change would not be a
 * silent bug here.
 *
 * TODO(org-settings): no organization-level timezone field exists in the API
 * yet (`packages/shared-types/src/generated/api.d.ts` has no such field --
 * the closest is `trading_day_timezone` on `/portfolios/{id}/risk`, itself
 * hardcoded server-side to this same zone, `hunter_api/schemas/portfolio.py`).
 * Once a real per-organization setting exists, read it instead of this
 * constant; every helper below funnels through `BRASILIA_TIME_ZONE`, so that
 * will be a one-line change here rather than a hunt across the app.
 */
export const BRASILIA_TIME_ZONE = "America/Sao_Paulo";

/** Plain-Portuguese label for `BRASILIA_TIME_ZONE` -- never the IANA name, never "BRT" in prose (brief item 8). */
export const BRASILIA_LABEL = "Brasília";

interface BrasiliaParts {
  year: string;
  month: string;
  day: string;
  hour: string;
  minute: string;
  second: string;
}

const PARTS_FORMATTER = new Intl.DateTimeFormat("en-US", {
  timeZone: BRASILIA_TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
});

function brasiliaParts(date: Date): BrasiliaParts | null {
  if (Number.isNaN(date.getTime())) return null;
  const parts = PARTS_FORMATTER.formatToParts(date);
  const get = (type: string): string => parts.find((p) => p.type === type)?.value ?? "";
  return { year: get("year"), month: get("month"), day: get("day"), hour: get("hour"), minute: get("minute"), second: get("second") };
}

/**
 * "08/09 02:05" -- day/month + hour:minute in Brasília (brief item 2's short
 * form; replaces the old UTC-only `formatWhenShort`). Deterministic in any
 * runtime timezone (SSR-safe, verified in `tests/time.test.ts` by spying on
 * `Date#getTimezoneOffset`): `Intl.DateTimeFormat`'s explicit `timeZone`
 * option resolves Brasília's own offset regardless of the container's or the
 * browser's own zone.
 */
export function formatBrasiliaShort(iso: string): string | null {
  const p = brasiliaParts(new Date(iso));
  return p ? `${p.day}/${p.month} ${p.hour}:${p.minute}` : null;
}

/** "08/09/2026 02:05:05" -- full Brasília date+time (brief item 2's long form; System operator detail, tooltips). */
export function formatBrasiliaLong(iso: string): string | null {
  const p = brasiliaParts(new Date(iso));
  return p ? `${p.day}/${p.month}/${p.year} ${p.hour}:${p.minute}:${p.second}` : null;
}

/** "08/09/2026" -- Brasília calendar day only, no time (an instant collapsed to its Brasília day; distinct from a field the API already sends as a bare day, e.g. `trading_day`). */
export function formatBrasiliaDate(iso: string): string | null {
  const p = brasiliaParts(new Date(iso));
  return p ? `${p.day}/${p.month}/${p.year}` : null;
}

/**
 * Combined Brasília + UTC line for a chart's crosshair label (brief item 6:
 * "tooltip shows Brasília and UTC"), e.g. "08/09 02:05:05 Brasília ·
 * 05:05:05 UTC". `Date`'s own UTC getters back the UTC half -- no dependency
 * on `lib/format.ts` needed for three digits.
 */
export function formatBrasiliaWithUtcTooltip(iso: string): string {
  const date = new Date(iso);
  const p = brasiliaParts(date);
  if (!p) return "--";
  const utcHour = String(date.getUTCHours()).padStart(2, "0");
  const utcMinute = String(date.getUTCMinutes()).padStart(2, "0");
  const utcSecond = String(date.getUTCSeconds()).padStart(2, "0");
  return `${p.day}/${p.month} ${p.hour}:${p.minute}:${p.second} Brasília · ${utcHour}:${utcMinute}:${utcSecond} UTC`;
}

// --- Chart axis ticks (candles-chart.tsx, portfolio-equity-chart.tsx,
// lab-curve-chart.tsx): lightweight-charts' own `TickMarkType` enum values
// (0 Year, 1 Month, 2 DayOfMonth, 3 Time, 4 TimeWithSeconds), duplicated here
// as plain numbers instead of importing the enum -- this module backs every
// timestamp in the product, not only charts, and should not depend on a
// charting library. ---

const TICK_YEAR = new Intl.DateTimeFormat("pt-BR", { timeZone: BRASILIA_TIME_ZONE, year: "numeric" });
const TICK_MONTH = new Intl.DateTimeFormat("pt-BR", { timeZone: BRASILIA_TIME_ZONE, month: "short" });
const TICK_DAY = new Intl.DateTimeFormat("pt-BR", { timeZone: BRASILIA_TIME_ZONE, day: "2-digit" });
const TICK_TIME = new Intl.DateTimeFormat("pt-BR", { timeZone: BRASILIA_TIME_ZONE, hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const TICK_TIME_SECONDS = new Intl.DateTimeFormat("pt-BR", {
  timeZone: BRASILIA_TIME_ZONE,
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
});

/** `epochSeconds` is a chart's own `UTCTimestamp` (whole seconds since the UTC epoch). */
export function formatBrasiliaTick(epochSeconds: number, tickMarkType: number): string {
  const date = new Date(epochSeconds * 1000);
  switch (tickMarkType) {
    case 0:
      return TICK_YEAR.format(date);
    case 1:
      return TICK_MONTH.format(date);
    case 2:
      return TICK_DAY.format(date);
    case 4:
      return TICK_TIME_SECONDS.format(date);
    default:
      return TICK_TIME.format(date);
  }
}
