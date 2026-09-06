import { notFound } from "next/navigation";

import { OpportunitiesError } from "@/components/opportunities/opportunities-error";
import { WhyPanel } from "@/components/opportunities/why-panel";
import { isApiError } from "@/lib/api-error";
import { getOpportunity } from "@/lib/api/opportunities";
import type { OpportunityDetailOut } from "@/lib/api/opportunities-types";
import { resolveOrgContext } from "@/lib/api/org-context";
import { getCurrentRegime } from "@/lib/api/regime";
import type { RegimeOut } from "@/lib/api/regime-types";
import { logger } from "@/lib/logger";

export interface OpportunityDetailPageProps {
  params: Promise<{ orgSlug: string; id: string }>;
}

type DetailLoad = { ok: true; detail: OpportunityDetailOut } | { ok: false; notFound: true } | { ok: false; notFound: false; reason: string };

async function loadDetail(id: string, orgId: string): Promise<DetailLoad> {
  try {
    const detail = await getOpportunity(id, { org_id: orgId });
    return { ok: true, detail };
  } catch (error) {
    if (isApiError(error) && error.status === 404) return { ok: false, notFound: true };
    const reason = isApiError(error) ? (error.detail ?? error.message) : "erro desconhecido";
    logger.error("opportunity_detail_load_failed", { error: reason, id });
    return { ok: false, notFound: false, reason };
  }
}

/**
 * Finds the `/regime` row backing `detail.regime_id`, if the classifier's
 * current scope still confirms it -- `null` (never thrown) when `/regime`
 * itself fails, so a broken regime read degrades only `WhyContext`'s regime
 * half, never the whole detail page.
 */
async function loadCurrentRegime(regimeId: string | null | undefined): Promise<RegimeOut | null> {
  if (!regimeId) return null;
  try {
    const current = await getCurrentRegime();
    return current.items.find((item) => item.id === regimeId) ?? null;
  } catch (error) {
    logger.error("opportunity_detail_regime_load_failed", { error: error instanceof Error ? error.message : String(error) });
    return null;
  }
}

/** `/[orgSlug]/opportunities/[id]` (docs/plans/M2.md T2.7) -- the "por que estamos olhando isso?" explainability panel. */
export default async function OpportunityDetailPage({ params }: OpportunityDetailPageProps) {
  const { orgSlug, id } = await params;
  const membership = await resolveOrgContext(orgSlug);
  if (!membership) notFound();

  const load = await loadDetail(id, membership.organization.id);
  if (!load.ok && load.notFound) notFound();
  // Resolved here, not inside a nested async component: a Server Component
  // rendered directly (as this page is, in every test that exercises it) has
  // no RSC boundary to resolve an async child component against.
  const currentRegime = load.ok ? await loadCurrentRegime(load.detail.regime_id) : null;

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-xl font-semibold text-fg">
        {load.ok ? (
          <>
            {load.detail.symbol} <span className="text-sm font-normal text-fg-subtle">{load.detail.exchange}</span>
          </>
        ) : (
          "Oportunidade"
        )}
      </h1>
      {!load.ok ? (
        <OpportunitiesError reason={load.reason} />
      ) : (
        <WhyPanel detail={load.detail} currentRegime={currentRegime} orgId={membership.organization.id} />
      )}
    </div>
  );
}
