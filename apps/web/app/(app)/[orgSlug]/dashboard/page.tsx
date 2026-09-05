import { notFound } from "next/navigation";

import { EmptyStateCard } from "@/components/dashboard/empty-state-card";
import { MembersCard } from "@/components/dashboard/members-card";
import { OrganizationCard } from "@/components/dashboard/organization-card";
import { QuickLinks } from "@/components/dashboard/quick-links";
import { WorkspaceCard } from "@/components/dashboard/workspace-card";
import { LiveStatus } from "@/components/system/live-status";
import { isApiError } from "@/lib/api-error";
import { listMembers } from "@/lib/api/members";
import { resolveOrgContext } from "@/lib/api/org-context";
import { getMarketStatus } from "@/lib/api/system";
import type { MarketStatusResponse, WorkspaceOut } from "@/lib/api/types";
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
 * The M0 dashboard shell (docs/plans/M0.md T09, docs/PRODUCT.md §4: shell at
 * M0, complete at M5). Only cards this milestone can back with real data --
 * no PnL, no charts, no invented numbers (CLAUDE.md's "no fake anything").
 */
export default async function DashboardPage({ params }: DashboardPageProps) {
  const { orgSlug } = await params;
  const membership = await resolveOrgContext(orgSlug);
  if (!membership) notFound();

  const orgId = membership.organization.id;
  const [workspaceLoad, membersLoad, marketStatus] = await Promise.all([
    loadWorkspace(orgId),
    loadMembers(orgId),
    marketStatusOrNull(),
  ]);

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-xl font-semibold text-fg">Dashboard</h1>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <OrganizationCard organization={membership.organization} role={membership.role} />
        {renderWorkspace(workspaceLoad)}
        {membersLoad.ok ? (
          <MembersCard orgSlug={orgSlug} count={membersLoad.count} atLeast={membersLoad.atLeast} />
        ) : (
          <EmptyStateCard title="Membros" message={`Membros indisponível: ${membersLoad.reason}`} />
        )}
        {marketStatus ? (
          <LiveStatus variant="full" initial={marketStatus} />
        ) : (
          <EmptyStateCard title="Mercados" message="Mercados: status indisponível no momento." />
        )}
        <EmptyStateCard title="Portfolio" message="Nenhum portfolio ainda · Milestone 3" />
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
