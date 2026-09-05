import { clerkSetup, setupClerkTestingToken } from "@clerk/testing/playwright";
import { expect, test } from "@playwright/test";

/**
 * Real, non-fake Clerk dev-instance keys, distinct from `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`
 * / `CLERK_SECRET_KEY` (which the running dev server / `node` CI job load
 * with the documented FAKE values -- see public.spec.ts). These must point
 * at an actual Clerk dev instance with:
 *   - Email address + email verification code as the sign-up strategy
 *     (docs/MVP.md §2: "confirmação de e-mail").
 *   - Test mode enabled, so `+clerk_test` emails and the fixed OTP `424242`
 *     are accepted (https://clerk.com/docs/testing/test-emails-and-phones).
 * See this file's README.md and the task report's CONCERNS section for the
 * exact Clerk Dashboard settings and where to put these as GitHub secrets.
 */
const PUBLISHABLE_KEY = process.env.CLERK_E2E_PUBLISHABLE_KEY;
const SECRET_KEY = process.env.CLERK_E2E_SECRET_KEY;
const HAS_CLERK_E2E_KEYS = Boolean(PUBLISHABLE_KEY && SECRET_KEY);

const CLERK_TEST_OTP = "424242";

function clerkTestEmail(): string {
  // Clerk test-mode convention: any address containing "+clerk_test" before
  // the "@" always accepts CLERK_TEST_OTP and never sends a real email.
  // Suffixed with the run's own timestamp so repeat runs don't collide on
  // an existing user.
  return `hunter.e2e+clerk_test_${Date.now()}@example.com`;
}

test.describe("signup -> onboarding -> dashboard (docs/MVP.md §2 critical flow)", () => {
  test.skip(!HAS_CLERK_E2E_KEYS, "CLERK_E2E keys not configured");

  test.beforeAll(async () => {
    // Narrows `string | undefined` -> `string` locally (exactOptionalPropertyTypes) --
    // `HAS_CLERK_E2E_KEYS` above is what actually decides, via `test.skip`, whether this ever runs.
    if (!PUBLISHABLE_KEY || !SECRET_KEY) return;
    await clerkSetup({ publishableKey: PUBLISHABLE_KEY, secretKey: SECRET_KEY });
  });

  test("creates an account, completes the six onboarding steps, and lands on an honest M0 dashboard", async ({ page }) => {
    await setupClerkTestingToken({ page });

    // ---- Sign up (Clerk-hosted <SignUp> at app/(auth)/sign-up) ----
    const email = clerkTestEmail();
    await page.goto("/sign-up");
    await page.getByLabel(/email address/i).fill(email);
    await page.getByRole("button", { name: /continue/i }).click();

    // Email-code verification screen. Clerk's own testing docs cover this
    // exact "+clerk_test" + fixed-OTP combination; if the dev instance is
    // configured with a different sign-up strategy (e.g. password-first),
    // this step needs the corresponding field filled in before it.
    await page.getByLabel(/verification code/i).fill(CLERK_TEST_OTP);
    await page.getByRole("button", { name: /continue/i }).click();

    // Root page.tsx: signed-in + no memberships -> /onboarding.
    await page.waitForURL(/\/onboarding/, { timeout: 15_000 });

    // ---- Step 1: organization + workspace name ----
    const orgName = `Hunter E2E ${Date.now()}`;
    await page.getByLabel(/nome da organização/i).fill(orgName);
    await page.getByRole("button", { name: /avançar/i }).click();

    // ---- Step 2: objective ----
    await expect(page.getByRole("heading", { name: /qual é o seu objetivo/i })).toBeVisible();
    await page.getByRole("radio", { name: /explorar/i }).click();
    await page.getByRole("button", { name: /avançar/i }).click();

    // ---- Step 3: virtual capital (preset $25,000) ----
    await expect(page.getByRole("heading", { name: /capital virtual/i })).toBeVisible();
    await page.getByRole("button", { name: "$25,000" }).click();
    await page.getByRole("button", { name: /avançar/i }).click();

    // ---- Step 4: risk profile (Balanced) ----
    await expect(page.getByRole("heading", { name: /perfil de risco/i })).toBeVisible();
    await page.getByRole("radio", { name: /balanceado/i }).click();
    await page.getByRole("button", { name: /avançar/i }).click();

    // ---- Step 5: exchanges (Binance + Bybit) ----
    await expect(page.getByRole("heading", { name: /exchanges monitoradas/i })).toBeVisible();
    await page.getByLabel("Binance").check();
    await page.getByLabel("Bybit").check();
    await page.getByRole("button", { name: /avançar/i }).click();

    // ---- Step 6: summary -> finish ----
    await expect(page.getByRole("heading", { name: /confirme e finalize/i })).toBeVisible();
    await page.getByRole("button", { name: /finalizar/i }).click();

    // ---- Dashboard: honest M0 shell, no invented data (CLAUDE.md) ----
    await page.waitForURL(/\/[^/]+\/dashboard$/, { timeout: 15_000 });
    await expect(page.getByText(orgName)).toBeVisible();
    await expect(page.getByText("Mercados monitorados: 0")).toBeVisible();
    await expect(page.getByText(/pnl/i)).toHaveCount(0);

    // ---- /system and /settings/members are reachable post-onboarding ----
    const orgSlugMatch = /\/([^/]+)\/dashboard$/.exec(page.url());
    const orgSlug = orgSlugMatch?.[1];
    if (!orgSlug) throw new Error(`could not extract org slug from dashboard URL: ${page.url()}`);

    await page.goto(`/${orgSlug}/system`);
    await expect(page.getByRole("heading", { name: "System" })).toBeVisible();

    await page.goto(`/${orgSlug}/settings/members`);
    await expect(page.getByRole("heading", { name: /membros/i })).toBeVisible();
  });
});
