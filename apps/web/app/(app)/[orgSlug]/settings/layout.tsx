import { notFound } from "next/navigation";
import type { ReactNode } from "react";

import { SettingsNav } from "@/components/settings/settings-nav";
import { resolveOrgContext } from "@/lib/api/org-context";

export interface SettingsLayoutProps {
  children: ReactNode;
  params: Promise<{ orgSlug: string }>;
}

/** Chrome for every `/settings/*` page (docs/PRODUCT.md §4) -- sub-nav only; each page fetches its own data. */
export default async function SettingsLayout({ children, params }: SettingsLayoutProps) {
  const { orgSlug } = await params;
  const membership = await resolveOrgContext(orgSlug);
  if (!membership) notFound();

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-xl font-semibold text-foreground">Settings</h1>
      <SettingsNav orgSlug={orgSlug} />
      <div className="max-w-2xl">{children}</div>
    </div>
  );
}
