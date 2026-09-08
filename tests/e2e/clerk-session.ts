import { setupClerkTestingToken } from "@clerk/testing/playwright";
import { expect, type Page } from "@playwright/test";

/**
 * The signup + onboarding walk `markets.spec.ts` and `signup-onboarding.spec.ts`
 * each carry inline, extracted here so `radar.spec.ts` and `opportunity.spec.ts`
 * (docs/plans/M2.md T2.8) do not become a third and fourth copy.
 *
 * Deliberately NOT applied back to the two existing specs: this task may not
 * edit them (`.claude/state/brief-T2.8b.md` scope), and a helper that half the
 * suite uses is still better than one nobody does. Not a `*.spec.ts`, so
 * Playwright's default `testMatch` never collects it as a test file.
 *
 * There are **no credentials in this file**. It reads Clerk *test-mode* keys
 * from the environment (`CLERK_E2E_PUBLISHABLE_KEY`/`CLERK_E2E_SECRET_KEY`) and
 * signs up with `+clerk_test` addresses plus the fixed `424242` OTP, which is
 * Clerk's own documented testing mechanism — never a real inbox, never a real
 * user.
 */
export const PUBLISHABLE_KEY = process.env.CLERK_E2E_PUBLISHABLE_KEY;
export const SECRET_KEY = process.env.CLERK_E2E_SECRET_KEY;
export const HAS_CLERK_E2E_KEYS = Boolean(PUBLISHABLE_KEY && SECRET_KEY);

const CLERK_TEST_OTP = "424242";

function clerkTestEmail(prefix: string): string {
  return `hunter.e2e+clerk_test_${prefix}_${Date.now()}@example.com`;
}

/** Signs a fresh account up through onboarding and lands on `/<orgSlug>/dashboard`, returning `orgSlug`. Mirrors `markets.spec.ts` step for step. */
export async function signUpAndOnboard(page: Page, label: string): Promise<string> {
  await setupClerkTestingToken({ page });

  await page.goto("/sign-up");
  await page.getByLabel(/email address/i).fill(clerkTestEmail(label));
  await page.getByRole("button", { name: "Continue", exact: true }).click();

  await page.getByLabel(/verification code/i).fill(CLERK_TEST_OTP);
  await page.getByRole("button", { name: "Continue", exact: true }).click();

  await page.waitForURL(/\/onboarding/, { timeout: 15_000 });

  await page.getByLabel(/nome da organização/i).fill(`Hunter E2E ${label} ${Date.now()}`);
  await page.getByRole("button", { name: /avançar/i }).click();

  await expect(page.getByRole("heading", { name: /qual é o seu objetivo/i })).toBeVisible();
  await page.getByRole("radio", { name: /explorar/i }).click();
  await page.getByRole("button", { name: /avançar/i }).click();

  await expect(page.getByRole("heading", { name: /capital virtual/i })).toBeVisible();
  await page.getByRole("button", { name: "$25,000" }).click();
  await page.getByRole("button", { name: /avançar/i }).click();

  await expect(page.getByRole("heading", { name: /perfil de risco/i })).toBeVisible();
  await page.getByRole("radio", { name: /balanceado/i }).click();
  await page.getByRole("button", { name: /avançar/i }).click();

  await expect(page.getByRole("heading", { name: /exchanges monitoradas/i })).toBeVisible();
  await page.getByLabel("Binance").check();
  await page.getByRole("button", { name: /avançar/i }).click();

  await expect(page.getByRole("heading", { name: /confirme e finalize/i })).toBeVisible();
  await page.getByRole("button", { name: /finalizar/i }).click();

  await page.waitForURL(/\/[^/]+\/dashboard$/, { timeout: 15_000 });
  const orgSlugMatch = /\/([^/]+)\/dashboard$/.exec(page.url());
  const orgSlug = orgSlugMatch?.[1];
  if (!orgSlug) throw new Error(`could not extract org slug from dashboard URL: ${page.url()}`);
  return orgSlug;
}
