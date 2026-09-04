import type { ReactNode } from "react";

import { MobileNav } from "@/components/layout/mobile-nav";
import { Sidebar } from "@/components/layout/sidebar";
import { Topbar } from "@/components/layout/topbar";
import { resolveOrgContext } from "@/lib/api/org-context";
import { ready } from "@/lib/api/system";
import type { ReadyStatus } from "@/lib/api/types";
import { logger } from "@/lib/logger";
import { visibleNavItems } from "@/lib/nav-registry";
import { getServerSession } from "@/lib/server/auth";
import { notFound, redirect } from "next/navigation";

/**
 * `ready()` (lib/api/system.ts) already turns a failed fetch into a
 * `{database: false, redis: false}` reading -- the one thing it can't
 * survive is `API_URL` being unset, which it deliberately throws on. That's
 * exactly right for the System page (a real misconfiguration should be
 * loud there), but the topbar's status dot renders on every page under this
 * layout, so a missing `API_URL` must not 500 the whole app shell -- fall
 * back to a "down" reading instead.
 */
async function readyOrDown(): Promise<ReadyStatus | null> {
  try {
    return await ready();
  } catch (error) {
    logger.error("topbar_ready_check_failed", { error: error instanceof Error ? error.message : String(error) });
    return null;
  }
}

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
  const systemStatus = await readyOrDown();

  return (
    <div className="flex h-dvh w-full overflow-hidden bg-bg text-fg">
      <Sidebar items={items} orgSlug={orgSlug} className="hidden md:flex" />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar orgSlug={orgSlug} systemStatus={systemStatus}>
          <MobileNav items={items} orgSlug={orgSlug} />
        </Topbar>
        <main className="flex-1 overflow-y-auto p-4 md:p-6">{children}</main>
      </div>
    </div>
  );
}
