import { notFound } from "next/navigation";

import { AutoRefresh } from "@/components/auto-refresh";
import { OpportunitiesError } from "@/components/opportunities/opportunities-error";
import { OpportunitiesFilters, type OpportunitiesFiltersState } from "@/components/opportunities/opportunities-filters";
import { OpportunitiesTable } from "@/components/opportunities/opportunities-table";
import { DEFAULT_AUTO_REFRESH_INTERVAL_MS } from "@/lib/auto-refresh-interval";
import { isApiError } from "@/lib/api-error";
import { listOpportunities } from "@/lib/api/opportunities";
import type { OpportunitiesParams, OpportunityListPage } from "@/lib/api/opportunities-types";
import type { OpportunityStage, OpportunityStatus } from "@/lib/api/radar-types";
import { resolveOrgContext } from "@/lib/api/org-context";
import { logger } from "@/lib/logger";

export interface OpportunitiesPageProps {
  params: Promise<{ orgSlug: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}

const OPPORTUNITIES_PAGE_LIMIT = 200;

function first(value: string | string[] | undefined): string {
  return Array.isArray(value) ? (value[0] ?? "") : (value ?? "");
}

function many<T extends string>(value: string | string[] | undefined): T[] {
  if (value === undefined) return [];
  return (Array.isArray(value) ? value : [value]) as T[];
}

function parseFilters(sp: Record<string, string | string[] | undefined>): OpportunitiesFiltersState {
  return {
    q: first(sp.q),
    scoreMin: first(sp.score_min),
    status: many<OpportunityStatus>(sp.status),
    stage: many<OpportunityStage>(sp.stage),
    exchange: first(sp.exchange),
  };
}

function toParams(filters: OpportunitiesFiltersState, orgId: string): OpportunitiesParams {
  const params: OpportunitiesParams = { org_id: orgId, limit: OPPORTUNITIES_PAGE_LIMIT };
  if (filters.q) params.q = filters.q;
  if (filters.scoreMin) params.score_min = filters.scoreMin;
  if (filters.status.length) params.status = filters.status;
  if (filters.stage.length) params.stage = filters.stage;
  if (filters.exchange) params.exchange = filters.exchange;
  return params;
}

type OpportunitiesLoad = { ok: true; page: OpportunityListPage } | { ok: false; reason: string };

async function loadOpportunities(params: OpportunitiesParams): Promise<OpportunitiesLoad> {
  try {
    const page = await listOpportunities(params);
    return { ok: true, page };
  } catch (error) {
    const reason = isApiError(error) ? (error.detail ?? error.message) : "erro desconhecido";
    logger.error("opportunities_page_load_failed", { error: reason });
    return { ok: false, reason };
  }
}

/** `/[orgSlug]/opportunities` (docs/plans/M2.md T2.7) -- the compact opportunities index; the full "why" panel lives at `/opportunities/[id]`. */
export default async function OpportunitiesPage({ params, searchParams }: OpportunitiesPageProps) {
  const { orgSlug } = await params;
  const membership = await resolveOrgContext(orgSlug);
  if (!membership) notFound();

  const sp = await searchParams;
  const filters = parseFilters(sp);
  const opportunitiesParams = toParams(filters, membership.organization.id);

  const load = await loadOpportunities(opportunitiesParams);
  const hasFilters = filters.q !== "" || filters.scoreMin !== "" || filters.status.length > 0 || filters.stage.length > 0 || filters.exchange !== "";

  return (
    <div className="flex flex-col gap-4">
      <AutoRefresh intervalMs={DEFAULT_AUTO_REFRESH_INTERVAL_MS} />
      <h1 className="text-xl font-semibold text-fg">Opportunities</h1>
      <OpportunitiesFilters state={filters} />
      {!load.ok ? (
        <OpportunitiesError reason={load.reason} />
      ) : (
        <OpportunitiesTable
          orgSlug={orgSlug}
          initialItems={load.page.items}
          initialCursor={load.page.next_cursor ?? null}
          hasFilters={hasFilters}
          baseParams={opportunitiesParams}
        />
      )}
    </div>
  );
}
