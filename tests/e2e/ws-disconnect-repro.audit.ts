import { clerkSetup, setupClerkTestingToken } from "@clerk/testing/playwright";
import { expect, test, type Page, type WebSocket as PwWebSocket } from "@playwright/test";

import { HAS_CLERK_E2E_KEYS, PUBLISHABLE_KEY, SECRET_KEY } from "./clerk-session";

/**
 * T3.44d -- diagnosis-only, read-only against the LOCAL stack (never the
 * VPS). Descartável (não é `*.spec.ts`; roda via `ws-repro.config.ts`'s
 * `testMatch`, mesmo padrão de `design-audit.audit.ts`).
 *
 * Instruments Playwright's OWN `page.on("websocket")` tracking (no app code
 * touched for this step) to answer, with ground truth from the browser's
 * real WebSocket objects, exactly what the VPS `ws_closed` log could not:
 * WHEN each socket in this tab closes, its code/reason/wasClean, and what
 * the app was doing (which route, how long since page load) at that instant.
 * Runs >= 3 minutes of real navigation across the pages that mount a
 * realtime channel (`useMarketChannels`): topbar (every page, compact) and
 * the dashboard's own full `LiveStatus`.
 *
 * Local copy of `clerk-session.ts#signUpAndOnboard`, NOT the shared helper:
 * the shared one's `.fill(CLERK_TEST_OTP)` on the verification-code field
 * hangs forever against this Clerk dev instance (`design-audit.audit.ts`'s
 * own doc comment, 2026-09-08: the OTP field ignores `fill`, must be typed
 * key by key with `page.keyboard.type` -- it auto-submits at the 6th digit).
 * Confirmed here again: the run below timed out at exactly that `.click()`
 * with the shared helper before this fix.
 */
const PROBE_MS = 3 * 60_000 + 20_000; // >= 3 minutes of navigation, + slack

async function signUpAndOnboard(page: Page, label: string): Promise<string> {
  await setupClerkTestingToken({ page });
  const cont = () => page.getByRole("button", { name: "Continue", exact: true });
  await page.goto("/sign-up");
  await page.getByLabel(/email address/i).fill(`hunter.e2e+clerk_test_${label}_${Date.now()}@example.com`);
  await cont().click();
  const otp = page.getByLabel(/verification code/i);
  await otp.waitFor();
  await otp.click();
  await page.keyboard.type("424242", { delay: 80 });
  await page.waitForURL(/\/onboarding/, { timeout: 20_000 });
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
  await page.waitForURL(/\/[^/]+\/dashboard$/, { timeout: 20_000 });
  const m = /\/([^/]+)\/dashboard$/.exec(page.url());
  const orgSlug = m?.[1];
  if (!orgSlug) throw new Error(`could not extract org slug from dashboard URL: ${page.url()}`);
  return orgSlug;
}

interface SocketRecord {
  id: number;
  url: string;
  openedAtMs: number;
  route: string;
  closedAtMs?: number;
  code?: number;
  reason?: string;
  wasClean?: boolean;
  error?: string;
}

test.describe.serial("T3.44d ws close repro", () => {
  test.skip(!HAS_CLERK_E2E_KEYS, "CLERK_E2E keys not configured");

  test.beforeAll(async () => {
    if (!PUBLISHABLE_KEY || !SECRET_KEY) return;
    await clerkSetup({ publishableKey: PUBLISHABLE_KEY, secretKey: SECRET_KEY });
  });

  test("every websocket open/close over >= 3 minutes of real navigation", async ({ page }) => {
    test.setTimeout(PROBE_MS + 80_000);

    const t0 = Date.now();
    const sockets: SocketRecord[] = [];
    const consoleLines: string[] = [];
    let nextId = 1;
    let currentRoute = "(pre-auth)";

    page.on("console", (msg) => {
      const text = msg.text();
      if (text.includes("realtime_") || text.includes("ws_") || text.includes("\"level\"")) {
        consoleLines.push(`+${((Date.now() - t0) / 1000).toFixed(1)}s [${currentRoute}] ${text}`);
      }
    });

    page.on("websocket", (ws: PwWebSocket) => {
      const rec: SocketRecord = { id: nextId++, url: ws.url(), openedAtMs: Date.now() - t0, route: currentRoute };
      sockets.push(rec);
      console.log(`[open]  #${rec.id} +${(rec.openedAtMs / 1000).toFixed(1)}s route=${rec.route} url=${rec.url}`);
      ws.on("close", () => {
        rec.closedAtMs = Date.now() - t0;
        const durationS = ((rec.closedAtMs - rec.openedAtMs) / 1000).toFixed(1);
        console.log(`[close] #${rec.id} +${(rec.closedAtMs / 1000).toFixed(1)}s route(now)=${currentRoute} lifetime=${durationS}s`);
      });
      ws.on("socketerror", (err: string) => {
        rec.error = err;
        console.log(`[error] #${rec.id} +${((Date.now() - t0) / 1000).toFixed(1)}s ${err}`);
      });
    });

    await signUpAndOnboard(page, "wsrepro");
    currentRoute = "dashboard(post-onboard)";

    // Real in-app navigation ONLY -- `nav-links.tsx`'s `<Link>`s, clicked
    // through the desktop Sidebar, exactly how Everton actually moves
    // between pages. Deliberately never `page.goto()` after the first load:
    // that is Playwright's own recipe for a HARD browser navigation (typed
    // URL / full reload), which is a materially different event from a
    // Next.js soft client-side transition and was already shown (first run
    // of this script, before this fix) to open a second, independent pair of
    // sockets on top of the first -- exactly what a real page reload does,
    // and not the question this script exists to answer.
    const nav = page.getByRole("navigation", { name: "Navegação principal" });
    const labels = ["Markets", "Radar", "Dashboard", "System", "Carteira", "Dashboard"];
    let i = 0;
    while (Date.now() - t0 < PROBE_MS) {
      const label = labels[i % labels.length] ?? "Dashboard";
      currentRoute = label;
      await nav.getByRole("link", { name: label, exact: true }).click();
      await page.waitForLoadState("load", { timeout: 30_000 }).catch(() => undefined);
      i += 1;
      await page.waitForTimeout(20_000);
    }

    console.log("\n===== SUMMARY =====");
    for (const s of sockets) {
      const lifetime = s.closedAtMs !== undefined ? `${((s.closedAtMs - s.openedAtMs) / 1000).toFixed(1)}s` : "still open";
      console.log(
        `#${s.id} opened +${(s.openedAtMs / 1000).toFixed(1)}s (route=${s.route}) lifetime=${lifetime}${s.error ? ` error=${s.error}` : ""}`,
      );
    }
    console.log(`\ntotal sockets opened: ${sockets.length}`);
    console.log(`sockets still open at end: ${sockets.filter((s) => s.closedAtMs === undefined).length}`);

    console.log("\n===== realtime_*/ws_* console lines =====");
    for (const line of consoleLines) console.log(line);
  });
});
