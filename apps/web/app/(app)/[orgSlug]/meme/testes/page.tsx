import { notFound } from "next/navigation";

import { AutoRefresh } from "@/components/auto-refresh";
import { PaperLabel } from "@/components/meme-desk/paper-label";
import { MemeDeskTabs } from "@/components/meme-tests/meme-desk-tabs";
import { isDayString } from "@/components/meme-tests/meme-tests-format";
import { MemeTestsSection } from "@/components/meme-tests/meme-tests-section";
import { SectionUnavailable } from "@/components/ui/section-unavailable";
import { loadMemeTests } from "@/lib/api/meme-tests";
import { resolveOrgContext } from "@/lib/api/org-context";

export interface MemeTestsPageProps {
  params: Promise<{ orgSlug: string }>;
  searchParams: Promise<{ day?: string; set?: string; cursor?: string }>;
}

/** Brief T4.13 §2: the desk refreshes every 5 s; the record of the day changes at the pace of the loop (a fill or a close per minute at most), so a calmer 15 s keeps an open bet's provisional exit honest without hammering the API. */
const TESTS_REFRESH_MS = 15_000;
/** One API page (`MAX_PAGE_SIZE`): the table never renders more than 200 rows (CLAUDE.md: virtualize past 200); the section says so and points at the CSV. */
const TESTS_PAGE_LIMIT = 200;

/**
 * `/[orgSlug]/meme/testes?day=&set=&cursor=` -- the complete record of every
 * test of a Brasília day (brief T4.13), on its own route; the same section
 * renders under `/meme/mesa?tab=testes`. Server Component; VIEWER+.
 */
export default async function MemeTestsPage({ params, searchParams }: MemeTestsPageProps) {
  const [{ orgSlug }, query] = await Promise.all([params, searchParams]);
  const membership = await resolveOrgContext(orgSlug);
  if (!membership) notFound();

  const day = isDayString(query.day) ? query.day : undefined;
  const ruleSet = query.set && query.set.length > 0 ? query.set : null;
  const tests = await loadMemeTests(membership.organization.id, { day, ruleSet: ruleSet ?? undefined, limit: TESTS_PAGE_LIMIT, cursor: query.cursor });

  return (
    <div className="flex flex-col gap-6">
      <AutoRefresh intervalMs={TESTS_REFRESH_MS} />
      <div className="flex flex-col gap-2">
        <div>
          <h1 className="text-xl font-semibold text-fg">Mesa — testes</h1>
          <p className="text-xs text-fg-muted">Cada aposta do dia com entrada, saída, motivo, PnL em SOL e US$, R e o que o Lab dizia no minuto da entrada. Tudo exportável.</p>
        </div>
        <PaperLabel />
      </div>
      <MemeDeskTabs orgSlug={orgSlug} active="testes" />
      {tests.ok ? (
        <MemeTestsSection orgSlug={orgSlug} host="testes" data={tests.data} ruleSet={ruleSet} />
      ) : (
        <SectionUnavailable title="Testes" reason={`falha ao carregar (${tests.reason})`} />
      )}
    </div>
  );
}
