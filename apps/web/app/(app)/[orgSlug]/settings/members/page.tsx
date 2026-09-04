import { notFound } from "next/navigation";

import { InviteForm } from "@/components/settings/invite-form";
import { InvitationsList } from "@/components/settings/invitations-list";
import { MembersTable } from "@/components/settings/members-table";
import { listInvitations } from "@/lib/api/invitations";
import { listMembers } from "@/lib/api/members";
import { resolveOrgContext, roleAtLeast } from "@/lib/api/org-context";

export interface MembersSettingsPageProps {
  params: Promise<{ orgSlug: string }>;
}

const PAGE_SIZE = 200;

/** Settings > Members (docs/PRODUCT.md §4) -- roster + invitations, both role-gated to mirror `apps/api/hunter_api/routers/{members,invitations}.py`. */
export default async function MembersSettingsPage({ params }: MembersSettingsPageProps) {
  const { orgSlug } = await params;
  const membership = await resolveOrgContext(orgSlug);
  if (!membership) notFound();

  const orgId = membership.organization.id;
  const canInvite = roleAtLeast(membership.role, "ADMIN");
  const [members, invitations] = await Promise.all([
    listMembers(orgId, { limit: PAGE_SIZE }),
    canInvite ? listInvitations(orgId, { limit: PAGE_SIZE }) : Promise.resolve({ items: [] }),
  ]);

  return (
    <div className="flex flex-col gap-6">
      <section>
        <h2 className="mb-2 text-sm font-medium text-fg-muted">Membros ({members.items.length}{members.next_cursor ? "+" : ""})</h2>
        <MembersTable orgId={orgId} members={members.items} currentRole={membership.role} />
      </section>

      {canInvite && (
        <section>
          <h2 className="mb-2 text-sm font-medium text-fg-muted">Convidar</h2>
          <InviteForm orgId={orgId} currentRole={membership.role} />
        </section>
      )}

      {canInvite && (
        <section>
          <h2 className="mb-2 text-sm font-medium text-fg-muted">Convites pendentes</h2>
          <InvitationsList orgId={orgId} invitations={invitations.items} />
        </section>
      )}
    </div>
  );
}
