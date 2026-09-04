/**
 * Decides whether `app/(app)/[orgSlug]/layout.tsx` should bounce a
 * membership that hasn't finished onboarding back into the wizard
 * (`?org=<slug>` resumes it at step 2 -- `app/(onboarding)/onboarding/[[...step]]/page.tsx`).
 *
 * Pure and string-based (no Next.js request/response types) so it's
 * unit-testable without a request context. `pathname` comes from the
 * `x-pathname` header `middleware.ts` sets on every request -- a Server
 * Component layout has no built-in way to read the current path. The
 * pathname guard exists so this never loops on a route that is itself part
 * of onboarding, even nested under `[orgSlug]` in the future.
 */
export function resolveOnboardingRedirect(orgSlug: string, onboardingCompleted: boolean, pathname: string): string | null {
  if (onboardingCompleted) return null;
  if (pathname.startsWith("/onboarding")) return null;
  return `/onboarding?org=${orgSlug}`;
}
