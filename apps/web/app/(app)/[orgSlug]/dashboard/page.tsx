import Link from "next/link";
import { notFound } from "next/navigation";

import { AnomaliesTile, loadAnomaliesTile } from "@/components/dashboard/anomalies-tile";
import { EmptyStateCard } from "@/components/dashboard/empty-state-card";
import { HotOpportunitiesTile, loadHotOpportunitiesTile } from "@/components/dashboard/hot-opportunities-tile";
import { MembersCard } from "@/components/dashboard/members-card";
import { OrganizationCard } from "@/components/dashboard/organization-card";
import { QuickLinks } from "@/components/dashboard/quick-links";
import { RegimeTile, loadRegimeTile } from "@/components/dashboard/regime-tile";
import { SystemHealthLine } from "@/components/dashboard/system-health-line";
import { WorkspaceCard } from "@/components/dashboard/workspace-card";
import { LiveStatus } from "@/components/system/live-status";
import { Button } from "@/components/ui/button";
import { isApiError } from "@/lib/api-error";
import { listMembers } from "@/lib/api/members";
import { resolveOrgContext } from "@/lib/api/org-context";
import { getMarketStatus, ready, wasReadyCheckAttempted } from "@/lib/api/system";
import type { MarketStatusResponse, ReadyStatus, WorkspaceOut } from "@/lib/api/types";
import { listWorkspaces } from "@/lib/api/workspaces";
import { logger } from "@/lib/logger";

export interface DashboardPageProps {
  params: Promise<{ orgSlug: string }>;
}

const MEMBERS_PAGE_SIZE = 200;

type WorkspaceLoad = { ok: true; workspace: WorkspaceOut | undefined } | { ok: false; reason: string };
type MembersLoad = { ok: true; count: number; atLeast: boolean } | { ok: false; reason: string };

/**
 * Isolated from `listMembers`/`marketStatusOrNull` (T1.5 review F3):
 * `listWorkspaces` and `listMembers` used to sit unprotected in the page's
 * `Promise.all` -- a single failing endpoint rejected the whole dashboard
 * render before any section (including the ones that DID succeed) could
 * show its own honest state.
 */
async function loadWorkspace(orgId: string): Promise<WorkspaceLoad> {
  try {
    const page = await listWorkspaces(orgId, { limit: 1 });
    return { ok: true, workspace: page.items[0] };
  } catch (error) {
    const reason = isApiError(error) ? (error.detail ?? error.message) : "erro desconhecido";
    logger.error("dashboard_workspaces_load_failed", { error: reason });
    return { ok: false, reason };
  }
}

async function loadMembers(orgId: string): Promise<MembersLoad> {
  try {
    const page = await listMembers(orgId, { limit: MEMBERS_PAGE_SIZE });
    return { ok: true, count: page.items.length, atLeast: page.next_cursor != null };
  } catch (error) {
    const reason = isApiError(error) ? (error.detail ?? error.message) : "erro desconhecido";
    logger.error("dashboard_members_load_failed", { error: reason });
    return { ok: false, reason };
  }
}

/**
 * The M1 dashboard shell (docs/plans/M0.md T09, docs/PRODUCT.md §4: shell at
 * M0, complete at M5). Hierarchy per T1.5b's joint decision #2: Markets and
 * coverage first (what the product actually does today), a one-line health
 * summary next (diagnosis detail lives in `/system`), org/workspace/members
 * below. No PnL/equity placeholder cards -- the nav already communicates
 * what M3 brings; an outlined "chega no M3" card was still occupying space
 * with an absence, which is not what docs/PRODUCT.md §7's "estados vazios
 * honestos" asks for on a screen that has real data to show instead.
 */
export default async function DashboardPage({ params }: DashboardPageProps) {
  const { orgSlug } = await params;
  const membership = await resolveOrgContext(orgSlug);
  if (!membership) notFound();

  const orgId = membership.organization.id;
  const [workspaceLoad, membersLoad, marketStatus, readiness, anomaliesLoad, hotOpportunitiesLoad, regimeLoad] = await Promise.all([
    loadWorkspace(orgId),
    loadMembers(orgId),
    marketStatusOrNull(),
    readyOrNull(),
    loadAnomaliesTile(),
    loadHotOpportunitiesTile(),
    loadRegimeTile(),
  ]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold text-fg">Dashboard</h1>
        <SystemHealthLine orgSlug={orgSlug} status={readiness} />
      </div>

      <section className="rounded-lg border border-border bg-bg-elevated p-4">
        <div className="flex items-center justify-between">
          <h2 className="text-xs font-medium uppercase tracking-wide text-fg-muted">Mercados</h2>
          <Button asChild variant="outline" size="sm">
            <Link href={`/${orgSlug}/markets`}>Ver mercados</Link>
          </Button>
        </div>
        <div className="mt-3">
          {marketStatus ? (
            <LiveStatus variant="full" initial={marketStatus} />
          ) : (
            <EmptyStateCard title="Cobertura" message="Mercados: status indisponível no momento." />
          )}
        </div>
      </section>

      {/*
       * Radar tiles (T2.7, brief line 12): anomalies/HOT/regime, right after
       * Mercados per the same hierarchy rule (T1.5b joint decision #2) --
       * what the product actually does today, before org/workspace/members
       * chrome. Each tile fetches and fails on its own (same isolation as
       * `loadWorkspace`/`loadMembers` above), so one down component never
       * takes the section with it.
       */}
      <div className="grid gap-4 md:grid-cols-3">
        <AnomaliesTile result={anomaliesLoad} />
        <HotOpportunitiesTile orgSlug={orgSlug} result={hotOpportunitiesLoad} />
        <RegimeTile result={regimeLoad} />
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <OrganizationCard organization={membership.organization} role={membership.role} />
        {renderWorkspace(workspaceLoad)}
        {membersLoad.ok ? (
          <MembersCard orgSlug={orgSlug} count={membersLoad.count} atLeast={membersLoad.atLeast} />
        ) : (
          <EmptyStateCard title="Membros" message={`Membros indisponível: ${membersLoad.reason}`} />
        )}
      </div>
      <QuickLinks orgSlug={orgSlug} />
    </div>
  );
}

function renderWorkspace(load: WorkspaceLoad) {
  if (!load.ok) return <EmptyStateCard title="Workspace" message={`Workspace indisponível: ${load.reason}`} />;
  if (!load.workspace) return <EmptyStateCard title="Workspace" message="Nenhum workspace ainda -- finalize o onboarding." />;
  return <WorkspaceCard workspace={load.workspace} />;
}

/**
 * `null` only when `/system/market-status` itself is unreachable (down,
 * misconfigured `API_URL`, etc.) -- a fetch failure is a different fact from
 * "zero exchanges reporting" (Astra's T1.5 review: don't render a fabricated
 * "0" for an outage), so this never claims a count it doesn't have. A
 * *successful* response with zero exchanges is the more specific honest
 * state `LiveStatus` renders itself ("Market worker: sem heartbeat") --
 * docs/plans/M1.md T1.5.
 */
async function marketStatusOrNull(): Promise<MarketStatusResponse | null> {
  try {
    return await getMarketStatus();
  } catch (error) {
    logger.error("dashboard_market_status_load_failed", { error: error instanceof Error ? error.message : String(error) });
    return null;
  }
}

/**
 * `null` only when `/ready` itself could not be attempted (`ready()`'s
 * `READY_CHECK_NOT_CONFIGURED` sentinel, T1.5b Astra must-fix #1) -- never
 * for a real, attempted "down"/"degraded" reading, so `SystemHealthLine`'s
 * `dotState` can tell "sem verificação" apart from a genuine outage
 * (joint decision #5). The `try`/`catch` is defense in depth mirroring
 * `[orgSlug]/layout.tsx`'s `readyOrDown` for the case `ready()` itself
 * rejects, which it no longer does on its own.
 */
async function readyOrNull(): Promise<ReadyStatus | null> {
  try {
    const status = await ready();
    return wasReadyCheckAttempted(status) ? status : null;
  } catch (error) {
    logger.error("dashboard_ready_check_failed", { error: error instanceof Error ? error.message : String(error) });
    return null;
  }
}
