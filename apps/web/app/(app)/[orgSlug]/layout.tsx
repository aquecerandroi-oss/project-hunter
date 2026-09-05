import type { ReactNode } from "react";

import { MobileNav } from "@/components/layout/mobile-nav";
import { Sidebar } from "@/components/layout/sidebar";
import { Topbar } from "@/components/layout/topbar";
import { resolveOrgContext } from "@/lib/api/org-context";
import { ready, wasReadyCheckAttempted } from "@/lib/api/system";
import type { ReadyStatus } from "@/lib/api/types";
import { logger } from "@/lib/logger";
import { visibleNavItems } from "@/lib/nav-registry";
import { resolveOnboardingRedirect } from "@/lib/onboarding-redirect";
import { getServerSession } from "@/lib/server/auth";
import { headers } from "next/headers";
import { notFound, redirect } from "next/navigation";

/**
 * `ready()` (lib/api/system.ts) never throws -- a missing `API_URL` and a
 * real fetch failure both resolve to a `ReadyStatus`, but only the latter is
 * an actual "checked and failed" reading. `null` here means the check was
 * never attempted (T1.5b Astra must-fix #1) so `topbar.tsx`'s `dotState` can
 * render "sem verificação" instead of a fabricated "Sistema indisponível" --
 * this `try`/`catch` is defense in depth for the (currently unreachable,
 * since `ready()` itself no longer throws) case of `ready()` rejecting.
 */
async function readyOrDown(): Promise<ReadyStatus | null> {
  try {
    const status = await ready();
    return wasReadyCheckAttempted(status) ? status : null;
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

  // An org whose onboarding never finished (docs/PRODUCT.md §3) has no
  // business rendering the dashboard/settings/system shell -- send the
  // caller back to resume the wizard at step 2 instead of showing an org
  // with unset objective/capital/risk profile as if it were ready.
  const pathname = (await headers()).get("x-pathname") ?? "";
  const onboardingRedirect = resolveOnboardingRedirect(orgSlug, membership.onboarding.completed, pathname);
  if (onboardingRedirect) redirect(onboardingRedirect);

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
