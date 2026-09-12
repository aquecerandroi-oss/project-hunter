import { notFound } from "next/navigation";

import { AutoRefresh } from "@/components/auto-refresh";
import { MemeFilterBar } from "@/components/meme/meme-filter-bar";
import { MemeOverviewStrip } from "@/components/meme/meme-overview-strip";
import { MemeSourcesPanel } from "@/components/meme/meme-sources-panel";
import { MemeTokensTable } from "@/components/meme/meme-tokens-table";
import { SectionUnavailable } from "@/components/ui/section-unavailable";
import { DEFAULT_AUTO_REFRESH_INTERVAL_MS } from "@/lib/auto-refresh-interval";
import { isApiError } from "@/lib/api-error";
import { getMemeOverview, listMemeTokens, type ListMemeTokensParams, loadMemeSources } from "@/lib/api/meme";
import { getMemeLoopState } from "@/lib/api/meme-desk";
import { MEME_TOKEN_SORTS, type MemeOverview, type MemeTokenList, type MemeTokenSort, type MemeTokenState } from "@/lib/api/meme-types";
import { resolveOrgContext } from "@/lib/api/org-context";
import { logger } from "@/lib/logger";

export interface MemePageProps {
  params: Promise<{ orgSlug: string }>;
  searchParams: Promise<{ state?: string; sort?: string }>;
}

const PAGE_LIMIT = 100;

function isMemeTokenState(value: string | undefined): value is MemeTokenState {
  return value === "curve" || value === "completed" || value === "migrated";
}

function isMemeTokenSort(value: string | undefined): value is MemeTokenSort {
  return (MEME_TOKEN_SORTS as readonly string[]).includes(value ?? "");
}

type OverviewLoad = { ok: true; data: MemeOverview } | { ok: false; reason: string };

async function loadOverview(orgId: string): Promise<OverviewLoad> {
  try {
    return { ok: true, data: await getMemeOverview(orgId) };
  } catch (error) {
    const reason = isApiError(error) ? (error.detail ?? error.message) : "erro desconhecido";
    logger.error("meme_overview_load_failed", { error: reason });
    return { ok: false, reason };
  }
}

type TokensLoad = { ok: true; page: MemeTokenList } | { ok: false; reason: string };

async function loadTokens(orgId: string, params: ListMemeTokensParams): Promise<TokensLoad> {
  try {
    return { ok: true, page: await listMemeTokens(orgId, params) };
  } catch (error) {
    const reason = isApiError(error) ? (error.detail ?? error.message) : "erro desconhecido";
    logger.error("meme_tokens_load_failed", { error: reason });
    return { ok: false, reason };
  }
}

/**
 * `/[orgSlug]/meme` — the Meme Radar (T4.3, `docs/plans/T4-MEME-RADAR.md`):
 * pump.fun monitoring only, no order, no wallet, no `RiskDecision`. Overview
 * strip (real numbers, one of two sourced shapes) + the tracked-tokens
 * table (server-driven `state`/`sort`, client-side virtualization + "load
 * more" for the rest).
 */
export default async function MemePage({ params, searchParams }: MemePageProps) {
  const { orgSlug } = await params;
  const membership = await resolveOrgContext(orgSlug);
  if (!membership) notFound();

  const sp = await searchParams;
  const state = isMemeTokenState(sp.state) ? sp.state : null;
  const sort: MemeTokenSort = isMemeTokenSort(sp.sort) ? sp.sort : "mcap";
  const orgId = membership.organization.id;

  const tokensParams: ListMemeTokensParams = { sort, limit: PAGE_LIMIT, ...(state ? { state } : {}) };

  // T4.3b: the sources panel and the loop's tick are read in the same server
  // render, so the page's own `AutoRefresh` is their polling too; each read
  // fails on its own (`loadMemeSources`/`getMemeLoopState` never throw).
  const [overviewResult, tokensResult, sourcesResult, loop] = await Promise.all([
    loadOverview(orgId),
    loadTokens(orgId, tokensParams),
    loadMemeSources(orgId),
    getMemeLoopState(orgId),
  ]);

  return (
    <div className="flex flex-col gap-6">
      <AutoRefresh intervalMs={DEFAULT_AUTO_REFRESH_INTERVAL_MS} />
      <div>
        <h1 className="text-xl font-semibold text-fg">Meme Radar</h1>
        <p className="text-xs text-fg-muted">Monitoramento do pump.fun — criação, curva de bonding e migração para o PumpSwap. Sem execução.</p>
      </div>

      {overviewResult.ok ? (
        <MemeOverviewStrip overview={overviewResult.data} />
      ) : (
        <SectionUnavailable title="Visão geral" reason={`falha ao carregar (${overviewResult.reason})`} />
      )}

      {sourcesResult.ok ? (
        <MemeSourcesPanel sources={sourcesResult.data} loop={loop} />
      ) : (
        <SectionUnavailable title="Fontes" reason={`falha ao carregar (${sourcesResult.reason})`} />
      )}

      <section className="flex flex-col gap-3">
        <MemeFilterBar orgSlug={orgSlug} state={state} sort={sort} />
        {tokensResult.ok ? (
          <MemeTokensTable
            orgId={orgId}
            orgSlug={orgSlug}
            initialItems={tokensResult.page.items}
            initialCursor={tokensResult.page.next_cursor ?? null}
            baseParams={tokensParams}
          />
        ) : (
          <SectionUnavailable title="Tokens" reason={`falha ao carregar (${tokensResult.reason})`} />
        )}
      </section>
    </div>
  );
}
