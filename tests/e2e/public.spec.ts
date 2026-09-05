import { expect, test } from "@playwright/test";

/**
 * Same documented fake Clerk publishable key used by `.github/workflows/ci.yml`'s
 * `node` job and allowlisted in `.gitleaks.toml` -- a value-format placeholder
 * (base64 of "clerk.example.com$"), never a real credential. It points Clerk
 * at a Frontend API host that doesn't exist, so the SDK's dev-browser
 * handshake can never complete client-side.
 */
const FAKE_CLERK_PUBLISHABLE_KEY = "pk_test_Y2xlcmsuZXhhbXBsZS5jb20k";

function usingFakeClerkKey(): boolean {
  const key = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;
  return !key || key === FAKE_CLERK_PUBLISHABLE_KEY;
}

test.describe("public surfaces (no auth required)", () => {
  test("/_design renders the design tokens page", async ({ page }) => {
    const response = await page.goto("/_design");
    expect(response?.ok()).toBe(true);
    // docs/DESIGN.md §4 -- app/globals.css's shared <title> ("Project
    // Hunter") doesn't change per route, so the honest check is the page's
    // own h1 (components/design/design-preview.tsx: "HUNTER -- Design Tokens"),
    // not document.title.
    await expect(page.getByRole("heading", { level: 1 })).toContainText(/design/i);
  });

  test("/sign-in renders Clerk's sign-in form", async ({ page }) => {
    test.skip(usingFakeClerkKey(), "CLERK_E2E keys not configured");
    await page.goto("/sign-in");
    await expect(page.getByLabel(/email address/i)).toBeVisible();
  });

  test("/sign-in with the documented fake key never mounts a form (honest failure, not a hang)", async ({ page }) => {
    test.skip(!usingFakeClerkKey(), "real Clerk keys are configured for this run; the fake-key fallback doesn't apply");

    const response = await page.goto("/sign-in");
    // middleware.ts's clerkMiddleware sets this response header the moment
    // it can't find a dev-browser JWT for the instance -- the same signal
    // that, in a real browser, triggers Clerk's client-side handshake
    // redirect. With a fake Frontend API host that redirect can never
    // complete, so we assert the honest, observable server-side fact
    // instead of a client navigation that will never happen.
    expect(response?.headers()["x-clerk-auth-reason"]).toBe("dev-browser-missing");

    // And the form itself must never silently render as if auth worked.
    await expect(page.getByLabel(/email address/i)).not.toBeVisible();
  });
});
