import { notFound } from "next/navigation";

import { AutoRefresh } from "@/components/auto-refresh";
import { ClosedTodaySection, RecentDecisionsSection } from "@/components/meme-desk/closed-today-section";
import { DeskOverviewStrip } from "@/components/meme-desk/desk-overview-strip";
import { ManualBuyDialog } from "@/components/meme-desk/manual-buy-dialog";
import { partitionDesk } from "@/components/meme-desk/meme-desk-format";
import { OpenBetsSection } from "@/components/meme-desk/open-bets-section";
import { PaperLabel } from "@/components/meme-desk/paper-label";
import { ProposalsSection } from "@/components/meme-desk/proposals-section";
import { MemeDeskTabs } from "@/components/meme-tests/meme-desk-tabs";
import { isDayString } from "@/components/meme-tests/meme-tests-format";
import { MemeTestsSection } from "@/components/meme-tests/meme-tests-section";
import { MemeSourcesPanel } from "@/components/meme/meme-sources-panel";
import { SectionUnavailable } from "@/components/ui/section-unavailable";
import { isApiError } from "@/lib/api-error";
import { loadMemeSources } from "@/lib/api/meme";
import { getMemeDesk, getMemeLoopState } from "@/lib/api/meme-desk";
import type { MemeDesk } from "@/lib/api/meme-desk-types";
import { loadMemeTests } from "@/lib/api/meme-tests";
import { resolveOrgContext, roleAtLeast } from "@/lib/api/org-context";
import { logger } from "@/lib/logger";

export interface MemeDeskPageProps {
  params: Promise<{ orgSlug: string }>;
  /** T4.13: `?tab=testes` renders the day's test record in place of the desk (same section as `/meme/testes`). */
  searchParams: Promise<{ tab?: string; day?: string; set?: string; cursor?: string }>;
}

/** Contract §Tela / brief T4.7: "atualização a cada 5 s" -- above `MIN_AUTO_REFRESH_INTERVAL_MS` (3 s); memes move fast and the loop ticks every minute, so 5 s keeps a countdown honest without hammering the API. */
const DESK_REFRESH_MS = 5_000;
const DESK_PAGE_LIMIT = 200;
/** The tests tab changes at the loop's pace (a fill or a close per minute at most) -- a calmer 15 s. */
const TESTS_REFRESH_MS = 15_000;

type DeskLoad = { ok: true; data: MemeDesk } | { ok: false; reason: string };

async function loadDesk(orgId: string): Promise<DeskLoad> {
  try {
    return { ok: true, data: await getMemeDesk(orgId, { limit: DESK_PAGE_LIMIT }) };
  } catch (error) {
    const reason = isApiError(error) ? (error.detail ?? error.message) : "erro desconhecido";
    logger.error("meme_desk_load_failed", { error: reason });
    return { ok: false, reason };
  }
}

/**
 * `/[orgSlug]/meme/mesa` -- the operator desk (T4.7, contract
 * `.claude/state/contrato-T4.6-T4.7-mesa-meme.md` §Tela): paper only.
 * Server Component for the load; the two sections with a countdown/one-tap
 * action are client islands. VIEWER+ sees everything; TRADER+ operates
 * (the API is the authority -- the buttons only say why they are off).
 */
export default async function MemeDeskPage({ params, searchParams }: MemeDeskPageProps) {
  const [{ orgSlug }, query] = await Promise.all([params, searchParams]);
  const membership = await resolveOrgContext(orgSlug);
  if (!membership) notFound();

  const orgId = membership.organization.id;
  const testsTab = query.tab === "testes";
  if (testsTab) {
    const day = isDayString(query.day) ? query.day : undefined;
    const ruleSet = query.set && query.set.length > 0 ? query.set : null;
    const tests = await loadMemeTests(orgId, { day, ruleSet: ruleSet ?? undefined, limit: DESK_PAGE_LIMIT, cursor: query.cursor });
    return (
      <div className="flex flex-col gap-6">
        <AutoRefresh intervalMs={TESTS_REFRESH_MS} />
        <DeskHeader />
        <MemeDeskTabs orgSlug={orgSlug} active="testes" />
        {tests.ok ? <MemeTestsSection orgSlug={orgSlug} host="mesa" data={tests.data} ruleSet={ruleSet} /> : <SectionUnavailable title="Testes" reason={`falha ao carregar (${tests.reason})`} />}
      </div>
    );
  }

  const canOperate = roleAtLeast(membership.role, "TRADER");
  // T4.3b: the sources line rides the same 5 s refresh; it renders on its own
  // so a desk failure still leaves the operator seeing what the radar reads.
  const [desk, loop, sources] = await Promise.all([loadDesk(orgId), getMemeLoopState(orgId), loadMemeSources(orgId)]);

  return (
    <div className="flex flex-col gap-6">
      <AutoRefresh intervalMs={DESK_REFRESH_MS} />
      <DeskHeader />
      <MemeDeskTabs orgSlug={orgSlug} active="mesa" />

      {sources.ok ? (
        <MemeSourcesPanel sources={sources.data} variant="line" />
      ) : (
        <SectionUnavailable title="Fontes" reason={`falha ao carregar (${sources.reason})`} compact />
      )}

      {!desk.ok ? (
        <SectionUnavailable title="Mesa" reason={`falha ao carregar (${desk.reason})`} />
      ) : (
        <DeskBody orgId={orgId} orgSlug={orgSlug} desk={desk.data} loopLastTickAt={loop.lastTickAt} loopReason={loop.reason} canOperate={canOperate} />
      )}
    </div>
  );
}

function DeskHeader() {
  return (
    <div className="flex flex-col gap-2">
      <div>
        <h1 className="text-xl font-semibold text-fg">Mesa — meme</h1>
        <p className="text-xs text-fg-muted">Aval da compra, espera e venda das apostas de papel do laço meme (pump.fun). O laço compra e vende na fotografia seguinte, nunca neste preço.</p>
      </div>
      <PaperLabel />
    </div>
  );
}

interface DeskBodyProps {
  orgId: string;
  orgSlug: string;
  desk: MemeDesk;
  loopLastTickAt: string | null;
  loopReason: "endpoint_missing" | "read_failed" | "shape_unknown" | null;
  canOperate: boolean;
}

function DeskBody({ orgId, orgSlug, desk, loopLastTickAt, loopReason, canOperate }: DeskBodyProps) {
  const loop = { lastTickAt: loopLastTickAt, reason: loopReason };
  const sections = partitionDesk(desk.items, desk.server_now);
  // T4.10b: a scale leg links to its probe's card only when that card is on this page.
  const knownBetIds = desk.items.flatMap((row) => (row.bet ? [row.bet.id] : []));
  return (
    <>
      <DeskOverviewStrip summary={desk.summary} loop={loop} serverNow={desk.server_now} />
      <ProposalsSection
        orgId={orgId}
        orgSlug={orgSlug}
        proposals={sections.proposals}
        awaitingFill={sections.awaitingFill}
        allRows={desk.items}
        loop={loop}
        serverNow={desk.server_now}
        canOperate={canOperate}
      />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-medium text-fg">Comprar manual</h2>
        <ManualBuyDialog orgId={orgId} canOperate={canOperate} />
      </div>
      <OpenBetsSection orgId={orgId} orgSlug={orgSlug} rows={sections.open} serverNow={desk.server_now} canOperate={canOperate} knownBetIds={knownBetIds} />
      <ClosedTodaySection orgSlug={orgSlug} rows={sections.closedToday} knownBetIds={knownBetIds} />
      <RecentDecisionsSection orgSlug={orgSlug} rows={sections.recent} knownBetIds={knownBetIds} />
    </>
  );
}
