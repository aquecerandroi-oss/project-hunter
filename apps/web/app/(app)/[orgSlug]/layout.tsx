import type { ReactNode } from "react";

import { MeUnavailableBanner, type MeUnavailableReason } from "@/components/layout/me-unavailable-banner";
import { MobileNav } from "@/components/layout/mobile-nav";
import { Sidebar } from "@/components/layout/sidebar";
import { Topbar } from "@/components/layout/topbar";
import { isApiError } from "@/lib/api-error";
import { resolveOrgContext } from "@/lib/api/org-context";
import { ready, wasReadyCheckAttempted } from "@/lib/api/system";
import type { MembershipOut, ReadyStatus } from "@/lib/api/types";
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

type MembershipLookup =
  | { kind: "ok"; membership: MembershipOut }
  | { kind: "not-a-member" }
  | { kind: "unauthenticated" }
  | { kind: "degraded"; reason: MeUnavailableReason };

/**
 * Brief T3.28b (2026-09-08 incident: a 429 from `/api/v1/me` under the API's
 * per-IP rate limit threw straight out of this layout -- `error.tsx` in this
 * same directory only wraps the segments BELOW the layout, never the layout
 * itself, so the throw skipped it entirely and landed on Next's bare
 * "Application error" screen, sidebar and all). `resolveOrgContext` (and the
 * `/me` fetch it wraps) now never escapes this function uncaught:
 * - a genuine "no membership for this slug" (`null`) still reads as 404.
 * - 401/403 means the token itself is no longer good enough (revoked
 *   between issuance and use, or the membership row itself vanished) --
 *   the SAME fact `getServerSession()` returning `null` already handles
 *   above, so it gets the same redirect, never a fabricated degraded state.
 * - 429/5xx/network is genuinely recoverable (SECURITY.md's "degradacao
 *   segura": the request will very likely succeed a few seconds later) --
 *   `degraded` lets the caller keep the shell up and offer a real retry
 *   instead of a dead end.
 */
async function resolveMembership(orgSlug: string): Promise<MembershipLookup> {
  try {
    const membership = await resolveOrgContext(orgSlug);
    return membership ? { kind: "ok", membership } : { kind: "not-a-member" };
  } catch (error) {
    if (isApiError(error) && (error.status === 401 || error.status === 403)) {
      return { kind: "unauthenticated" };
    }
    logger.error("org_layout_me_failed", {
      error: error instanceof Error ? error.message : String(error),
      status: isApiError(error) ? error.status : undefined,
    });
    const reason: MeUnavailableReason = isApiError(error) && error.status === 429 ? "rate-limited" : "unavailable";
    return { kind: "degraded", reason };
  }
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
  // A recoverable failure of that same fetch (429/5xx/network) is a THIRD
  // outcome, distinct from both -- see `resolveMembership`'s docstring.
  const lookup = await resolveMembership(orgSlug);
  if (lookup.kind === "unauthenticated") redirect("/sign-in");
  if (lookup.kind === "not-a-member") notFound();

  const env = process.env.HUNTER_ENV ?? "development";
  const systemStatus = await readyOrDown();

  // The degraded path has no membership row to read a role or onboarding
  // state from -- `VIEWER` is the least-privileged nav a real member could
  // ever have, so this never shows an item the caller might not actually be
  // allowed to reach once `/me` recovers (never MORE than "ok" would show,
  // only ever the same or less).
  let role: MembershipOut["role"] = "VIEWER";
  let main: ReactNode = children;

  if (lookup.kind === "ok") {
    // An org whose onboarding never finished (docs/PRODUCT.md §3) has no
    // business rendering the dashboard/settings/system shell -- send the
    // caller back to resume the wizard at step 2 instead of showing an org
    // with unset objective/capital/risk profile as if it were ready.
    const pathname = (await headers()).get("x-pathname") ?? "";
    const onboardingRedirect = resolveOnboardingRedirect(orgSlug, lookup.membership.onboarding.completed, pathname);
    if (onboardingRedirect) redirect(onboardingRedirect);
    role = lookup.membership.role;
  } else {
    main = <MeUnavailableBanner reason={lookup.reason} />;
  }

  const items = visibleNavItems(role, env);

  return (
    <div className="flex h-dvh w-full overflow-hidden bg-bg text-fg">
      <Sidebar items={items} orgSlug={orgSlug} className="hidden md:flex" />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar orgSlug={orgSlug} systemStatus={systemStatus}>
          <MobileNav items={items} orgSlug={orgSlug} />
        </Topbar>
        <main className="flex-1 overflow-y-auto p-4 md:p-6">{main}</main>
      </div>
    </div>
  );
}
