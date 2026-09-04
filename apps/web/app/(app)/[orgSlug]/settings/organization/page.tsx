import { notFound } from "next/navigation";

import { OrganizationForm } from "@/components/settings/organization-form";
import { resolveOrgContext, roleAtLeast } from "@/lib/api/org-context";

export interface OrganizationSettingsPageProps {
  params: Promise<{ orgSlug: string }>;
}

/** Settings > Organization -- name is the only mutable field in M0 (apps/api/hunter_api/schemas/organizations.py). */
export default async function OrganizationSettingsPage({ params }: OrganizationSettingsPageProps) {
  const { orgSlug } = await params;
  const membership = await resolveOrgContext(orgSlug);
  if (!membership) notFound();

  return (
    <OrganizationForm
      orgId={membership.organization.id}
      initialName={membership.organization.name}
      canEdit={roleAtLeast(membership.role, "ADMIN")}
    />
  );
}
