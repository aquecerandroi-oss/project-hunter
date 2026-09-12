import Link from "next/link";

import { buttonVariants } from "@/components/ui/button";
import { formatBrasiliaDate } from "@/lib/time";

import { type TestsHost, csvExportHref, ruleSetLabel, shiftDay, testsHref } from "./meme-tests-format";

export interface MemeTestsFiltersProps {
  orgSlug: string;
  host: TestsHost;
  /** `YYYY-MM-DD` (Brasília) the API answered for. */
  day: string;
  /** Today in Brasília, from the API's `server_now` -- "Hoje"/"Ontem" are relative to the server's clock, never the browser's. */
  serverNow: string;
  ruleSet: string | null;
  /** Rule-set names with at least one bet on the day (the API's `rule_sets`). */
  ruleSets: readonly string[];
}

function pill(active: boolean): string {
  return active ? "border-gold bg-gold-soft text-fg" : "border-border text-fg-muted hover:border-border-strong";
}

function todayBrasilia(serverNow: string): string | null {
  const date = formatBrasiliaDate(serverNow);
  if (!date) return null;
  const [d, m, y] = date.split("/");
  return `${y}-${m}-${d}`;
}

/**
 * Day (native date input, GET form -- the page re-fetches on navigation) and
 * rule set (links) filters, plus "Exportar CSV". Server Component: every
 * control is a form or a link, so the filters work before hydration and
 * without any client state (the `meme-filter-bar.tsx` convention).
 */
export function MemeTestsFilters({ orgSlug, host, day, serverNow, ruleSet, ruleSets }: MemeTestsFiltersProps) {
  const today = todayBrasilia(serverNow);
  const yesterday = today ? shiftDay(today, -1) : null;
  const action = host === "mesa" ? `/${orgSlug}/meme/mesa` : `/${orgSlug}/meme/testes`;
  return (
    <div className="flex flex-col gap-3 text-xs">
      <div className="flex flex-wrap items-end gap-3">
        <form method="get" action={action} className="flex flex-wrap items-end gap-2">
          {host === "mesa" && <input type="hidden" name="tab" value="testes" />}
          {ruleSet && <input type="hidden" name="set" value={ruleSet} />}
          <label className="flex flex-col gap-1 text-fg-muted">
            Dia (Brasília)
            <input type="date" name="day" defaultValue={day} className="rounded-md border border-border-input bg-bg-overlay px-2 py-1 font-mono text-[13px] text-fg" />
          </label>
          <button type="submit" className={buttonVariants({ variant: "outline", size: "sm" })}>
            Ver dia
          </button>
        </form>
        <div className="flex items-center gap-1">
          {today && (
            <Link href={testsHref({ orgSlug, host, day: today, ruleSet })} className={`rounded-full border px-2 py-1 ${pill(day === today)}`}>
              Hoje
            </Link>
          )}
          {yesterday && (
            <Link href={testsHref({ orgSlug, host, day: yesterday, ruleSet })} className={`rounded-full border px-2 py-1 ${pill(day === yesterday)}`}>
              Ontem
            </Link>
          )}
          <Link href={testsHref({ orgSlug, host, day: shiftDay(day, -1), ruleSet })} className="rounded-full border border-border px-2 py-1 text-fg-muted hover:border-border-strong" aria-label="dia anterior">
            ←
          </Link>
          <Link href={testsHref({ orgSlug, host, day: shiftDay(day, 1), ruleSet })} className="rounded-full border border-border px-2 py-1 text-fg-muted hover:border-border-strong" aria-label="dia seguinte">
            →
          </Link>
        </div>
        <a href={csvExportHref(orgSlug, day, ruleSet)} download className={`${buttonVariants({ variant: "outline", size: "sm" })} ml-auto`}>
          Exportar CSV
        </a>
      </div>
      <div className="flex flex-wrap items-center gap-1">
        <span className="mr-1 text-fg-muted">Conjunto:</span>
        <Link href={testsHref({ orgSlug, host, day })} className={`rounded-full border px-2 py-1 ${pill(ruleSet === null)}`}>
          Todos
        </Link>
        {ruleSets.map((name) => (
          <Link key={name} href={testsHref({ orgSlug, host, day, ruleSet: name })} className={`rounded-full border px-2 py-1 font-mono ${pill(ruleSet === name)}`}>
            {ruleSetLabel(name)}
          </Link>
        ))}
        {ruleSets.length === 0 && <span className="text-fg-subtle">nenhum conjunto apostou neste dia</span>}
      </div>
    </div>
  );
}
