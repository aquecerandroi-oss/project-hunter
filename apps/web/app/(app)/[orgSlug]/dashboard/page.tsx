import { notFound } from "next/navigation";

import { EmptyStateCard } from "@/components/dashboard/empty-state-card";
import { MembersCard } from "@/components/dashboard/members-card";
import { OrganizationCard } from "@/components/dashboard/organization-card";
import { QuickLinks } from "@/components/dashboard/quick-links";
import { WorkspaceCard } from "@/components/dashboard/workspace-card";
import { listMembers } from "@/lib/api/members";
import { resolveOrgContext } from "@/lib/api/org-context";
import { listWorkspaces } from "@/lib/api/workspaces";

export interface DashboardPageProps {
  params: Promise<{ orgSlug: string }>;
}

const MEMBERS_PAGE_SIZE = 200;

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
  const [workspaces, members] = await Promise.all([
    listWorkspaces(orgId, { limit: 1 }),
    listMembers(orgId, { limit: MEMBERS_PAGE_SIZE }),
  ]);
  const workspace = workspaces.items[0];

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-xl font-semibold text-fg">Dashboard</h1>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <OrganizationCard organization={membership.organization} role={membership.role} />
        {workspace ? (
          <WorkspaceCard workspace={workspace} />
        ) : (
          <EmptyStateCard title="Workspace" message="Nenhum workspace ainda -- finalize o onboarding." />
        )}
        <MembersCard orgSlug={orgSlug} count={members.items.length} atLeast={members.next_cursor != null} />
        <EmptyStateCard
          title="Mercados"
          message="Mercados monitorados: 0 · dados de mercado chegam no Milestone 1"
        />
        <EmptyStateCard title="Portfolio" message="Nenhum portfolio ainda · Milestone 3" />
      </div>
      <QuickLinks orgSlug={orgSlug} />
    </div>
  );
}
