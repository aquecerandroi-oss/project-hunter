import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

// Public per docs/plans/M0.md (T08): everything else requires a session.
// `/api/webhooks` stays public because Svix (not the browser) calls it and
// verifies its own signature (see docs/SECURITY.md §1) -- Clerk auth does not
// apply there.
const isPublicRoute = createRouteMatcher(["/", "/sign-in(.*)", "/sign-up(.*)", "/forgot-password(.*)", "/api/webhooks(.*)"]);

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
