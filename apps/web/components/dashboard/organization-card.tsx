import { Badge } from "@/components/ui/badge";
import type { OrganizationOut, OrganizationRole } from "@/lib/api/types";

export interface OrganizationCardProps {
  organization: OrganizationOut;
  role: OrganizationRole;
}

/** Honest org summary card -- name, plan and the caller's own role. No entitlements UI until Phase 3 billing. */
export function OrganizationCard({ organization, role }: OrganizationCardProps) {
  return (
    <section className="rounded-lg border border-border bg-bg-elevated p-4 transition-colors hover:border-border-strong">
      <h2 className="text-xs font-medium uppercase tracking-wide text-fg-muted">Organização</h2>
      <p className="mt-1 text-lg font-semibold text-fg">{organization.name}</p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Badge>{organization.plan}</Badge>
        <Badge variant="outline">Seu papel: {role}</Badge>
      </div>
    </section>
  );
}
