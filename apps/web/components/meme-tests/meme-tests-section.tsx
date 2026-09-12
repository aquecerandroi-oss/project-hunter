import Link from "next/link";

import { BrasiliaInstant } from "@/components/time/brasilia-instant";
import type { MemeTests } from "@/lib/api/meme-tests-types";
import { formatBrasiliaDate } from "@/lib/time";

import { walletsSourceLabel } from "./labels";
import { MemeTestsCards } from "./meme-tests-cards";
import { MemeTestsFilters } from "./meme-tests-filters";
import { type TestsHost, mergeTestRows, testsHref } from "./meme-tests-format";
import { MemeTestsTable } from "./meme-tests-table";
import { MemeTestsTotals } from "./meme-tests-totals";

export interface MemeTestsSectionProps {
  orgSlug: string;
  host: TestsHost;
  data: MemeTests;
  /** The `?set=` the page resolved (the API echoes it as `rule_set`). */
  ruleSet: string | null;
}

/**
 * The "Testes" content, shared by `/meme/testes` and `/meme/mesa?tab=testes`
 * (brief T4.13 §2): the API's own label, the filters, the day's totals, the
 * sources line, the dense table (>= md) or the cards (375 px), and the honest
 * pagination note. Server Component; the table is the only client island.
 */
export function MemeTestsSection({ orgSlug, host, data, ruleSet }: MemeTestsSectionProps) {
  const rows = mergeTestRows(data.items, data.real_items);
  const dayLabel = formatBrasiliaDate(`${data.day}T12:00:00-03:00`) ?? data.day;
  const shownPaper = data.items.length;
  const partial = data.next_cursor !== null && data.next_cursor !== undefined;
  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h2 className="text-sm font-medium text-fg">Testes de {dayLabel}</h2>
        <p role="note" className="rounded-md border border-warning/40 bg-warning-soft px-3 py-2 text-xs font-medium text-warning">
          {data.label}
        </p>
      </div>
      <MemeTestsFilters orgSlug={orgSlug} host={host} day={data.day} serverNow={data.server_now} ruleSet={ruleSet} ruleSets={data.rule_sets} />
      <MemeTestsTotals totals={data.totals} sources={data.sources} />
      <p className="text-[11px] text-fg-subtle">
        Reais: {walletsSourceLabel(data.sources.wallets)} · contexto do Lab lido de {data.sources.features_version} · Consultado em <BrasiliaInstant iso={data.server_now} />
      </p>
      {rows.length === 0 ? (
        <p className="rounded-md border border-border p-4 text-sm text-fg-muted">
          Nenhuma aposta {ruleSet ? `do conjunto ${ruleSet} ` : ""}entrou em {dayLabel} (dia de Brasília).
        </p>
      ) : (
        <>
          <div className="hidden md:block">
            <MemeTestsTable orgSlug={orgSlug} rows={rows} />
          </div>
          <div className="md:hidden">
            <MemeTestsCards orgSlug={orgSlug} rows={rows} />
          </div>
          <p className="text-[11px] text-fg-subtle">* saída provisória: a marca da última fotografia de uma aposta ainda aberta; PnL US$ provisório usa a cotação da entrada.</p>
        </>
      )}
      {partial && (
        <div className="flex flex-wrap items-center gap-3 text-xs text-fg-muted">
          <span>
            Mostrando {shownPaper} de {data.totals.bets} apostas de papel do dia — exporte o CSV para o dia inteiro.
          </span>
          <Link href={testsHref({ orgSlug, host, day: data.day, ruleSet, cursor: data.next_cursor })} className="underline">
            Próxima página
          </Link>
        </div>
      )}
    </section>
  );
}
