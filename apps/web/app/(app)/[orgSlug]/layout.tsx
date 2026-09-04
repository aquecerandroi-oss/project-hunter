import type { ReactNode } from "react";

import { MobileNav } from "@/components/layout/mobile-nav";
import { Sidebar } from "@/components/layout/sidebar";
import { Topbar } from "@/components/layout/topbar";
import { visibleNavItems } from "@/lib/nav-registry";
import { getServerSession } from "@/lib/server/auth";
import { redirect } from "next/navigation";

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

  // TODO(T09/T06): role should come from org membership once the orgs API
  // exists (docs/SECURITY.md §2) -- Clerk itself carries no role, we don't
  // use Clerk Organizations. Every M0 nav item has `minRole: "VIEWER"`, so
  // this placeholder does not hide anything yet.
  const role = "VIEWER" as const;
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
