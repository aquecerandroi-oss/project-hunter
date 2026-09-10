import { clerkSetup, setupClerkTestingToken } from "@clerk/testing/playwright";
import { expect, test } from "@playwright/test";

import { HAS_CLERK_E2E_KEYS, PUBLISHABLE_KEY, SECRET_KEY } from "./clerk-session";

/**
 * T3.72 — "Nova ordem paper" on the Carteira screen.
 *
 * Two preconditions this repo does not satisfy today, both self-skipped with
 * an honest reason rather than faked green:
 *
 * 1. **No mocked backend is possible for this flow.** `apps/web`'s wallet
 *    data (`lib/api/portfolio.ts`, `lib/api/manual-orders.ts`) is read in
 *    Server Components and Server Actions -- both run in the Next.js server
 *    process, never in the browser -- so Playwright's `page.route()` (which
 *    only intercepts requests the *browser* issues) cannot substitute a fake
 *    response the way `markets.spec.ts`'s WebSocket test intercepts a
 *    browser-side connection. A real run needs a real `apps/api` plus a real
 *    Postgres/Redis, exactly like `signup-onboarding.spec.ts` already
 *    requires for its own walk.
 * 2. **No paper wallet exists for a fresh sign-up.** `docs/plans/M0.md`'s
 *    onboarding creates only the organization/workspace (`README.md`'s own
 *    "Onboarding cria organização" row); the principal paper wallet is
 *    opened by an operator script (`infra/scripts/open_paper_wallet.py`,
 *    `RiskLimitsPresetOut`'s own docstring), not by sign-up. A brand-new
 *    E2E organization therefore lands on `PortfolioEmpty`, never the
 *    "Nova ordem paper" button this spec exercises.
 *
 * `E2E_MANUAL_ORDER_ORG_SLUG` names a pre-provisioned organization (real
 * compose stack, real open paper wallet, the signed-in E2E user a TRADER+
 * member of it) to run this for real against; absent it, the spec
 * self-skips instead of asserting against data that cannot exist yet. Also
 * gated by the same Chromium-cannot-reach-localhost condition noted in this
 * repo's own operating memory as of 2026-09-08 -- if that is still true when
 * this runs, the `page.goto` below fails with a connection error, not a
 * false pass.
 */
const ORG_SLUG = process.env.E2E_MANUAL_ORDER_ORG_SLUG;

test.describe("Nova ordem paper (T3.72)", () => {
  test.skip(!HAS_CLERK_E2E_KEYS, "CLERK_E2E keys not configured");
  test.skip(!ORG_SLUG, "E2E_MANUAL_ORDER_ORG_SLUG not set -- no pre-provisioned org with an open paper wallet to run this against");

  test.beforeAll(async () => {
    if (!PUBLISHABLE_KEY || !SECRET_KEY) return;
    await clerkSetup({ publishableKey: PUBLISHABLE_KEY, secretKey: SECRET_KEY });
  });

  test("files a manual paper order and shows the engine's decision", async ({ page }) => {
    await setupClerkTestingToken({ page });

    await page.goto(`/${ORG_SLUG}/portfolio`);
    await expect(page.getByRole("heading", { name: "Carteira" })).toBeVisible();

    const newOrderButton = page.getByRole("button", { name: "Nova ordem paper" });
    await expect(newOrderButton).toBeVisible();
    await expect(newOrderButton).toBeEnabled();
    await newOrderButton.click();

    const dialog = page.getByRole("dialog", { name: "Nova ordem paper" });
    await expect(dialog).toBeVisible();

    const marketSearch = dialog.getByLabel("Buscar mercado SPOT");
    await marketSearch.fill("USDT");
    await expect(dialog.getByRole("button", { name: /USDT/ }).first()).toBeVisible({ timeout: 10_000 });
    await dialog.getByRole("button", { name: /USDT/ }).first().click();

    const stopInput = dialog.getByLabel("Stop");
    await stopInput.fill("1");

    await dialog.getByRole("button", { name: "Enviar ordem" }).click();

    await expect(dialog.getByText(/Enviada, aguardando decisão do motor|Decisão recebida/)).toBeVisible({ timeout: 10_000 });
    await expect(dialog.getByText(/Aprovada|Recusada/)).toBeVisible({ timeout: 65_000 });
  });
});
