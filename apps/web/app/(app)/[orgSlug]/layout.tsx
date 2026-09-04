import type { ReactNode } from "react";

import { MobileNav } from "@/components/layout/mobile-nav";
import { Sidebar } from "@/components/layout/sidebar";
import { Topbar } from "@/components/layout/topbar";
import { resolveOrgContext } from "@/lib/api/org-context";
import { visibleNavItems } from "@/lib/nav-registry";
import { getServerSession } from "@/lib/server/auth";
import { notFound, redirect } from "next/navigation";

export interface OrgLayoutProps {
  children: ReactNode;
  params: Promise<{ orgSlug: string }>;
}

/**
 * App shell for every route under `(app)/[orgSlug]/**` (pages themselves are
 * T09's job -- this file only renders the sidebar/topbar/mobile-nav chrome
 * around `children`).
 */
export default async function OrgLayout({ children, params }: OrgLayoutProps) {
  const { orgSlug } = await params;
  const session = await getServerSession();
  if (!session) redirect("/sign-in");

  // The role comes from the caller's own membership row (`/api/v1/me`,
  // T06) -- Clerk itself carries no role, we don't use Clerk Organizations.
  // A slug the caller has no membership for reads as "page doesn't exist",
  // never a 500 (docs/DATABASE.md's RLS makes cross-tenant reads 404 too).
  const membership = await resolveOrgContext(orgSlug);
  if (!membership) notFound();

  const role = membership.role;
  const env = process.env.HUNTER_ENV ?? "development";
  const items = visibleNavItems(role, env);

  return (
    <div className="flex h-dvh w-full overflow-hidden bg-background text-foreground">
      <Sidebar items={items} orgSlug={orgSlug} className="hidden md:flex" />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar orgSlug={orgSlug}>
          <MobileNav items={items} orgSlug={orgSlug} />
        </Topbar>
        <main className="flex-1 overflow-y-auto p-4 md:p-6">{children}</main>
      </div>
    </div>
  );
}
