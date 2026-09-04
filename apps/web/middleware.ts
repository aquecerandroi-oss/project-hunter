import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

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
]);

export default clerkMiddleware(async (auth, req) => {
  if (!isPublicRoute(req)) {
    await auth.protect();
  }
});

export const config = {
  matcher: [
    // Skip Next.js internals and all static files, unless found in search params.
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    // Always run for API routes.
    "/(api|trpc)(.*)",
  ],
};
