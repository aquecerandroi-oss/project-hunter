/**
 * Pure helpers for the test record (T4.13): Brasília clock with seconds,
 * durations, US$ with an explicit sign, the merge of paper and REAL rows by
 * entry time, and the hrefs of the two hosts of the same section
 * (`/meme/testes` and `/meme/mesa?tab=testes`). No React, no fetch --
 * `tests/meme-tests-format.test.ts`.
 */
import { outcomeQualityLabel } from "@/components/meme-desk/labels";
import { formatDuration, formatR } from "@/components/meme-desk/meme-desk-format";
import type { MemeTestRow } from "@/lib/api/meme-tests-types";
import { formatMoney } from "@/lib/format";
import { formatBrasiliaLong } from "@/lib/time";

export type TestsHost = "testes" | "mesa";

export interface TestsHrefParams {
  orgSlug: string;
  host: TestsHost;
  day?: string | null | undefined;
  ruleSet?: string | null | undefined;
  cursor?: string | null | undefined;
}

/** "11:00:05" -- the Brasília clock with seconds (the day is the filter's); the full "dd/mm/aaaa hh:mm:ss" belongs in `title`. */
export function formatBrasiliaClock(iso: string | null | undefined): string {
  if (!iso) return "--";
  const long = formatBrasiliaLong(iso);
  return long ? long.slice(11) : "--";
}

/** "7 min 25 s" from whole seconds (the API's `duration_s`); `null` is an honest absence. */
export function formatDurationSeconds(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "sem duração";
  return formatDuration(seconds * 1000);
}

/** "+US$ 32.58" / "-US$ 5.00" / "US$ 0.00" -- explicit sign (DESIGN.md §2), decimal-safe via `formatMoney`. */
export function formatUsdSigned(value: string): string {
  const bare = formatMoney(value, { currency: "USD", decimals: 2 }).replace(/[^0-9.,-]/g, "");
  if (bare.startsWith("-")) return `-US$ ${bare.slice(1)}`;
  const zero = /^0+(\.0+)?$/.test(bare);
  return `${zero ? "" : "+"}US$ ${bare}`;
}

/** Paper rows (the page) and REAL rows (the day) as one list, newest entry first -- what the table and the cards render. */
export function mergeTestRows(items: readonly MemeTestRow[], realItems: readonly MemeTestRow[]): MemeTestRow[] {
  return [...items, ...realItems].sort((a, b) => {
    const byEntry = Date.parse(b.entry.at) - Date.parse(a.entry.at);
    return byEntry !== 0 ? byEntry : a.id.localeCompare(b.id);
  });
}

/** `YYYY-MM-DD` shifted by whole days (calendar arithmetic on the day string, timezone-free). */
export function shiftDay(day: string, days: number): string {
  const [y, m, d] = day.split("-").map(Number);
  const date = new Date(Date.UTC(y ?? 1970, (m ?? 1) - 1, (d ?? 1) + days));
  return date.toISOString().slice(0, 10);
}

/** Is `value` a `YYYY-MM-DD` the API will accept? Anything else falls back to today. */
export function isDayString(value: string | undefined | null): value is string {
  return typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(`${value}T00:00:00Z`));
}

/** The section's own href for either host, carrying only the params that are set. */
export function testsHref({ orgSlug, host, day, ruleSet, cursor }: TestsHrefParams): string {
  const params = new URLSearchParams();
  if (host === "mesa") params.set("tab", "testes");
  if (day) params.set("day", day);
  if (ruleSet) params.set("set", ruleSet);
  if (cursor) params.set("cursor", cursor);
  const query = params.toString();
  const path = host === "mesa" ? `/${orgSlug}/meme/mesa` : `/${orgSlug}/meme/testes`;
  return query ? `${path}?${query}` : path;
}

/** The route handler that proxies `GET /meme/tests.csv` with the session token (`app/(app)/[orgSlug]/meme/testes/export/route.ts`). */
export function csvExportHref(orgSlug: string, day: string, ruleSet: string | null): string {
  const params = new URLSearchParams({ day });
  if (ruleSet) params.set("rule_set", ruleSet);
  return `/${orgSlug}/meme/testes/export?${params.toString()}`;
}

export function betDetailHref(orgSlug: string, betId: string): string {
  return `/${orgSlug}/meme/mesa/aposta/${betId}`;
}

/** "wallet:6nAh8drz" reads as "REAL · carteira 6nAh8drz"; every other set is the experiment's own name (`meme_paper_v0/1`). */
export function ruleSetLabel(label: string): string {
  return label.startsWith("wallet:") ? `REAL · carteira ${label.slice("wallet:".length)}` : label;
}

export interface RMultipleView {
  text: string;
  /** `true` for both "sem leitura" (`—`) and `indeterminate` -- neither is a win/loss color. */
  muted: boolean;
}

/**
 * T4.16: an `indeterminate` row's `r_multiple` exists (the CHECK requires the
 * number) but is not trustworthy -- the API's own `outcome_quality_label`
 * replaces it, muted, everywhere an R prints (the dense table, the cards,
 * the bet's own record page).
 */
export function rMultipleView(row: Pick<MemeTestRow, "r_multiple" | "outcome_quality" | "outcome_quality_label">): RMultipleView {
  if (row.outcome_quality === "indeterminate") return { text: row.outcome_quality_label ?? outcomeQualityLabel("indeterminate"), muted: true };
  return row.r_multiple === null ? { text: "—", muted: true } : { text: formatR(row.r_multiple), muted: false };
}
