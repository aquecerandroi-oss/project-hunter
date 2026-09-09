import { expect, test } from "@playwright/test";
import { existsSync } from "node:fs";

/**
 * T3.44d, Deliverable 3 -- runs ONLY after the orchestrator has deployed this
 * task's fix to the VPS (`main` past the commit that includes `lib/ws.ts`,
 * `lib/realtime-health.ts`, `hooks/useMarketChannels.ts`,
 * `components/system/live-status.tsx`). Not run as part of this task --
 * VPS access here is READ-ONLY (this script never signs up, never writes;
 * see below), matching the operational rule the whole task ran under.
 *
 * What it needs, neither of which this task is authorized to produce against
 * the VPS itself:
 * - `E2E_BASE_URL=https://169.58.116.99`
 * - `VPS_STORAGE_STATE=<path to a Playwright storageState JSON>` -- cookies
 *   for an ALREADY-authenticated session against the VPS's real Clerk
 *   instance and an org the account is a real member of. Signing a fresh
 *   test user up against the VPS is a WRITE to its Postgres (`POST /orgs`,
 *   `PUT .../onboarding`), not a read -- out of scope for this task's
 *   read-only mandate. The orchestrator (or Everton, exporting his own
 *   browser's storage state, or a dedicated read-only VPS test account) is
 *   the one positioned to produce this safely.
 * - `VPS_ORG_SLUG=<the org slug that session belongs to>`
 *
 * Without both, this `test.skip`s with a clear reason -- same pattern as
 * every other Clerk-gated spec in this suite (`HAS_CLERK_E2E_KEYS`), never a
 * false red for a precondition it was never built to satisfy on its own.
 *
 * Samples the topbar's compact `LiveStatus` tooltip every 15s for 5 minutes
 * and records, per sample, Brasília wall-clock time + whether the "(tempo
 * real do navegador interrompido)" note is showing + (when it is) the exact
 * tooltip text this task's fix adds: "desde <Brasília> · último fechamento:
 * <reason> (<code>)". Prints a summary at the end. Correlate against the
 * VPS's own count for the same window with (read-only, run by the
 * orchestrator over ssh, never by this script):
 *
 *   ssh hunter-vps 'docker logs --since 6m hunter-api-1 2>&1 | grep ws_closed'
 *
 * Expectation this task's fix is judged against: every sample reads "ao
 * vivo" (no note), OR -- if a real disconnection happens during the 5
 * minutes -- the note appears with a `since`/reason the VPS's own
 * `ws_closed` count for the window explains, and the note clears again
 * within one grace window (`RECONNECT_GRACE_MS`, `lib/realtime-health.ts`)
 * of the client reconnecting, never staying stuck "interrompido" through a
 * reconnect that in fact succeeded.
 */
const STORAGE_STATE = process.env.VPS_STORAGE_STATE;
const ORG_SLUG = process.env.VPS_ORG_SLUG;
const READY = Boolean(STORAGE_STATE && ORG_SLUG && STORAGE_STATE && existsSync(STORAGE_STATE));

const SAMPLE_EVERY_MS = 15_000;
const DURATION_MS = 5 * 60_000;

interface Sample {
  atIso: string;
  interrompido: boolean;
  title: string | null;
}

test.describe("T3.44d Deliverable 3 -- VPS proof (post-deploy only)", () => {
  test.skip(!READY, "VPS_STORAGE_STATE/VPS_ORG_SLUG not configured -- see this file's own doc comment");

  test("topbar status sampled every 15s for 5 minutes against the real VPS", async ({ browser }) => {
    test.setTimeout(DURATION_MS + 60_000);
    if (!STORAGE_STATE) throw new Error("VPS_STORAGE_STATE must be set -- test.skip above should have caught this");
    const context = await browser.newContext({ storageState: STORAGE_STATE });
    const page = await context.newPage();
    await page.goto(`/${ORG_SLUG}/dashboard`, { waitUntil: "load", timeout: 30_000 });

    const samples: Sample[] = [];
    const t0 = Date.now();
    while (Date.now() - t0 < DURATION_MS) {
      const pill = page.locator("span[title]").filter({ hasText: /mercados/ }).first();
      const title = (await pill.getAttribute("title").catch(() => null)) ?? null;
      samples.push({ atIso: new Date().toISOString(), interrompido: Boolean(title?.includes("interrompido")), title });
      await page.waitForTimeout(SAMPLE_EVERY_MS);
    }

    console.log("\n===== T3.44d VPS samples (every 15s, 5min) =====");
    for (const s of samples) console.log(`${s.atIso} interrompido=${s.interrompido}${s.title ? ` title="${s.title}"` : ""}`);
    const downCount = samples.filter((s) => s.interrompido).length;
    console.log(`\n${samples.length} samples, ${downCount} showed "interrompido"`);
    console.log("Correlate against: ssh hunter-vps 'docker logs --since 6m hunter-api-1 2>&1 | grep ws_closed'");

    await context.close();
    expect(samples.length).toBeGreaterThan(0);
  });
});
