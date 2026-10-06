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

/**
 * What the web app under test is: `production` (`next start` / the Docker
 * image, which is what CI's e2e job runs -- NODE_ENV=production baked into
 * infra/docker/Dockerfile.web) or `development` (`pnpm --filter @hunter/web
 * dev`, the documented local flow in playwright.config.ts). Explicit
 * `E2E_WEB_MODE` wins; otherwise CI means production and a bare local run
 * means a dev server.
 */
function resolveWebMode(): "production" | "development" {
  const explicit = process.env.E2E_WEB_MODE;
  if (explicit === "production" || explicit === "development") return explicit;
  if (explicit) throw new Error(`E2E_WEB_MODE must be "production" or "development", got "${explicit}"`);
  return process.env.CI ? "production" : "development";
}
const webMode = resolveWebMode();

test.describe("public surfaces (no auth required)", () => {
  // docs/DESIGN.md §4: /_design is a design-review tool -- it renders in
  // development and 404s in production (app/%5Fdesign/page.tsx calls notFound()
  // when NODE_ENV === "production"). The two branches below assert each half
  // of that one contract; neither is weakened, the environment picks which
  // half applies.
  test("/_design follows its dev-only contract (renders in development, 404s in production)", async ({ page }) => {
    const response = await page.goto("/_design");
    if (webMode === "production") {
      expect(response?.status()).toBe(404);
      await expect(page.getByText("This page could not be found")).toBeVisible();
      await expect(page.getByRole("heading", { level: 1, name: /design/i })).toHaveCount(0);
      return;
    }
    expect(response?.status()).toBe(200);
    // app/globals.css's shared <title> ("Project Hunter") doesn't change per
    // route, so the honest check is the page's own h1
    // (components/design/design-preview.tsx: "HUNTER -- Design Tokens"),
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

    // middleware.ts's clerkMiddleware answers with a 307 to the instance's
    // handshake endpoint the moment it can't find a dev-browser JWT. With the
    // fake key that host (clerk.example.com) does not resolve, so a real
    // `page.goto` would die on ERR_NAME_NOT_RESOLVED while following it. We
    // therefore assert the honest, observable server-side fact without
    // following the redirect: the status, the handshake host and the reason
    // header. No sign-in form is ever served on this path.
    // clerkMiddleware only handshakes requests that look like a document
    // navigation from a browser (Accept text/html + sec-fetch-dest document);
    // the plain APIRequestContext is served the page directly, so mimic one.
    const response = await page.request.get("/sign-in", {
      maxRedirects: 0,
      headers: {
        accept: "text/html,application/xhtml+xml",
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128 Playwright",
      },
    });
    expect(response.status()).toBe(307);
    expect(response.headers()["x-clerk-auth-reason"]).toBe("dev-browser-missing");
    expect(response.headers()["location"]).toMatch(/^https:\/\/clerk\.example\.com\/v1\/client\/handshake/);
    expect(await response.text()).not.toMatch(/email address/i);
  });
});
