import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";

// Public per docs/plans/M0.md (T08): everything else requires a session.
// `/api/webhooks` stays public because Svix (not the browser) calls it and
// verifies its own signature (see docs/SECURITY.md §1) -- Clerk auth does not
// apply there.
const isPublicRoute = createRouteMatcher([
  "/",
  "/sign-in(.*)",
  "/sign-up(.*)",
  "/forgot-password(.*)",
  "/api/webhooks(.*)",
  // docs/DESIGN.md §4 -- the dev-only design-tokens preview
  // (app/%5Fdesign/page.tsx -> /_design; %5F is Next's documented escape
  // for a literal underscore in a URL segment without the folder being
  // treated as a private, un-routable one). It 404s on its own past dev via
  // `NODE_ENV === "production"`, so it doesn't need Clerk's auth gate too.
  "/_design(.*)",
  // `/accept-invite` is intentionally ABSENT from this list: accepting an
  // invitation (app/(auth)/accept-invite/page.tsx) requires a signed-in
  // caller (routers/invitations.py's `accept` matches the invitation's
  // email against the caller's own), so it must fall through to the
  // `auth.protect()` branch below like every other non-public route.
]);

export default clerkMiddleware(async (auth, req) => {
  if (!isPublicRoute(req)) {
    await auth.protect();
  }

  // Threaded through as a request header (Server Components/layouts have no
  // built-in way to read the current pathname) so
  // `app/(app)/[orgSlug]/layout.tsx` can tell whether it's already rendering
  // an onboarding route before redirecting an unfinished membership there.
  const requestHeaders = new Headers(req.headers);
  requestHeaders.set("x-pathname", req.nextUrl.pathname);
  return NextResponse.next({ request: { headers: requestHeaders } });
});

export const config = {
  matcher: [
    // Skip Next.js internals, the dev-only /_design preview (Clerk's dev handshake would
    // redirect a browser to the publishable key's domain), and all static files.
    "/((?!_next|_design|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    // Always run for API routes.
    "/(api|trpc)(.*)",
  ],
};
