import { clerkSetup, setupClerkTestingToken } from "@clerk/testing/playwright";
import { expect, test, type Page } from "@playwright/test";

/**
 * T1.7 item 6 (`.claude/state/brief-T1.7-tests.md`, `docs/plans/M1.md` T1.7
 * row): the markets list loads with real rows (the compose stack's
 * `market-worker` against real Binance), a row opens the detail page,
 * Ctrl/⌘K opens the command palette search, the quality badge ages when the
 * WebSocket is cut, and System shows the `market` worker.
 *
 * Gated exactly like `signup-onboarding.spec.ts`: real, non-fake Clerk
 * dev-instance keys via `CLERK_E2E_PUBLISHABLE_KEY`/`CLERK_E2E_SECRET_KEY`.
 * Absent keys -> `test.skip`, never a failure (CLAUDE.md: a test that cannot
 * run must say so honestly, not report red for a reason it wasn't built to
 * catch).
 */
const PUBLISHABLE_KEY = process.env.CLERK_E2E_PUBLISHABLE_KEY;
const SECRET_KEY = process.env.CLERK_E2E_SECRET_KEY;
const HAS_CLERK_E2E_KEYS = Boolean(PUBLISHABLE_KEY && SECRET_KEY);

const CLERK_TEST_OTP = "424242";

function clerkTestEmail(): string {
  return `hunter.e2e+clerk_test_${Date.now()}@example.com`;
}

/** Signs a fresh account up through onboarding and lands on `/<orgSlug>/dashboard`, returning `orgSlug`. Mirrors `signup-onboarding.spec.ts` step for step. */
async function signUpAndOnboard(page: Page): Promise<string> {
  await setupClerkTestingToken({ page });

  const email = clerkTestEmail();
  await page.goto("/sign-up");
  await page.getByLabel(/email address/i).fill(email);
  await page.getByRole("button", { name: /continue/i }).click();

  await page.getByLabel(/verification code/i).fill(CLERK_TEST_OTP);
  await page.getByRole("button", { name: /continue/i }).click();

  await page.waitForURL(/\/onboarding/, { timeout: 15_000 });

  const orgName = `Hunter E2E Markets ${Date.now()}`;
  await page.getByLabel(/nome da organização/i).fill(orgName);
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

test.describe("markets (docs/plans/M1.md T1.7)", () => {
  test.skip(!HAS_CLERK_E2E_KEYS, "CLERK_E2E keys not configured");

  test.beforeAll(async () => {
    if (!PUBLISHABLE_KEY || !SECRET_KEY) return;
    await clerkSetup({ publishableKey: PUBLISHABLE_KEY, secretKey: SECRET_KEY });
  });

  test("list loads with real rows, a row opens the detail, Ctrl/⌘K searches, and System shows the market worker", async ({ page }) => {
    const orgSlug = await signUpAndOnboard(page);

    // ---- list loads with real rows (the running market-worker's own data) --
    await page.goto(`/${orgSlug}/markets`);
    await expect(page.getByRole("heading", { name: "Markets", exact: true })).toBeVisible();
    const grid = page.getByRole("grid", { name: "Mercados monitorados" });
    await expect(grid).toBeVisible();
    const firstRowLink = grid.getByRole("row").nth(1).getByRole("link").first();
    await expect(firstRowLink).toBeVisible({ timeout: 15_000 });
    const symbol = (await firstRowLink.textContent())?.trim();
    expect(symbol).toBeTruthy();

    // ---- row click opens the detail -- asserts real content loaded, not
    // just the URL (Astra's second opinion, T1.7: a bare URL match would
    // also pass against an empty or errored detail page) -------------------
    await firstRowLink.click();
    await page.waitForURL(new RegExp(`/${orgSlug}/markets/[^/]+/${symbol}$`), { timeout: 10_000 });
    await expect(page.getByRole("heading", { name: new RegExp(symbol!) })).toBeVisible({
      timeout: 10_000,
    });

    // ---- back to the list, Ctrl/⌘K opens the command palette search -------
    // Searches for the FULL symbol just opened above and asserts that exact
    // result appears (Astra's second opinion: a bare "listbox is visible"
    // check would also pass with zero or wrong results).
    await page.goto(`/${orgSlug}/markets`);
    await page.keyboard.press("Control+k");
    const searchBox = page.getByRole("combobox", { name: "Buscar por símbolo" });
    await expect(searchBox).toBeVisible();
    await searchBox.fill(symbol!);
    const results = page.getByRole("listbox", { name: "Resultados" });
    await expect(results).toBeVisible();
    await expect(results.getByRole("option", { name: new RegExp(`^${symbol}\\b`) })).toBeVisible({
      timeout: 10_000,
    });
    await page.keyboard.press("Escape");

    // ---- System shows the market worker -------------------------------------
    await page.goto(`/${orgSlug}/system`);
    await expect(page.getByRole("heading", { name: "System" })).toBeVisible();
    await expect(page.getByRole("cell", { name: "market", exact: true }).first()).toBeVisible({
      timeout: 15_000,
    });
  });

  test("the quality badge ages when the WebSocket is cut", async ({ page }) => {
    // Intercepts every WebSocket handshake (whatever host:port NEXT_PUBLIC_WS_URL
    // bakes in) and closes it immediately -- Playwright's own recipe for
    // "the socket never reaches open", not a change to app config. Registered
    // BEFORE navigation so the very first connection attempt is caught.
    await page.routeWebSocket(/.*/, (ws) => {
      ws.close();
    });

    // Astra's second opinion (T1.7): cutting the WS alone is not enough
    // against a HEALTHY market-worker -- `AutoRefresh`
    // (`apps/web/components/auto-refresh.tsx`) re-runs the page's own
    // server-side fetch on an interval timed to land BEFORE
    // `stale_after_ms` on purpose (its own docstring: "a dead worker keeps
    // its last-known green badge" is exactly the bug it exists to prevent),
    // and that fetch would keep pulling genuinely fresh data from the
    // still-connected, still-healthy worker regardless of this browser
    // tab's own WebSocket. Next.js App Router's client-side re-fetches
    // (including `router.refresh()`) carry an `RSC` request header --
    // blocking those (never the initial full-page navigation, which has no
    // such header) isolates the WS as the only thing this test cuts.
    await page.route("**/*", (route) => {
      if (route.request().headers()["rsc"] === "1") return route.abort();
      return route.continue();
    });

    const orgSlug = await signUpAndOnboard(page);
    await page.goto(`/${orgSlug}/markets`);

    const grid = page.getByRole("grid", { name: "Mercados monitorados" });
    const firstRow = grid.getByRole("row").nth(1);
    await expect(firstRow).toBeVisible({ timeout: 15_000 });

    // Confirms the starting point is genuinely OK -- otherwise the "ages"
    // assertion below could pass vacuously against an already-stale row
    // (Astra's second opinion).
    await expect(firstRow.getByText("OK", { exact: true })).toBeVisible({ timeout: 10_000 });

    // With no live socket and no masking HTTP refresh, `QualityBadge`
    // re-derives from wall-clock age (`useAgeTicker`) alone -- no new tick
    // can ever arrive to keep it fresh. `market_stale_after_s` defaults to
    // 10s (docs/plans/M1.md); a generous window past that covers CI jitter
    // without a fixed short sleep.
    await expect(firstRow.getByText(/^atrasado /)).toBeVisible({ timeout: 30_000 });
  });
});
