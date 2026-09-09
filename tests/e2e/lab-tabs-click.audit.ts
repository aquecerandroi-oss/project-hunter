import { expect, test } from "@playwright/test";

/**
 * T3.51 -- Everton on the VPS: "aqui não tá funcionando, eu clico e não
 * resolve nada" clicking Concluídas/Abertas/Pendentes/Todas on `/lab`.
 * Descartável (não é `*.spec.ts`; roda via `lab-tabs-click.config.ts`, mesmo
 * padrão de `design-audit.audit.ts`/`ws-disconnect-repro.audit.ts`).
 *
 * Root cause confirmed by this repro (both against local, before the fix):
 * a tab was a `<button onClick={() => startTransition(() => router.push(...))}>`
 * with no fallback path. Even with `AutoRefresh` fully neutralized
 * (`document.visibilityState` forced to `"hidden"` via `addInitScript`, its
 * own pre-existing guard), `router.push()` never touched
 * `window.location`/`history.pushState` and never issued an RSC fetch at
 * all (confirmed with `window.fetch`/`history.pushState` patched from
 * `addInitScript` and a catch-all `context.route("**\/*", ...)`) -- the tree
 * sometimes re-rendered `aria-selected` locally via a stale/racy transition,
 * sometimes didn't move at all, but the URL and the loaded page never
 * changed either way. `AutoRefresh`'s own 12s `router.refresh()` tick then
 * reliably reset the tree to the default segment on the very next round,
 * reading as "nothing happens" exactly as reported. This refines the
 * brief's original hypothesis (`AutoRefresh` racing a *working* `push`):
 * the deeper problem is that a plain button-triggered `router.push()` had no
 * resilience at all on this page; `AutoRefresh` racing it is a real, latent
 * risk fixed independently (`shouldSkipAutoRefreshTick`,
 * `lib/auto-refresh-interval.ts`), not the sole cause.
 *
 * The fix: every tab (`lab-segment-tabs.tsx`) and the pager's
 * "Anterior"/"Próxima" (`lab-signal-pager.tsx`) are real `<Link href>`
 * anchors now -- `state` (the URL) is what drives `aria-selected`, and a
 * real anchor still works even if a client-side transition never runs.
 *
 * This same script is the deliverable 3 proof: after the orchestrator
 * rebuilds `web`, re-running it shows the URL carrying `?state=...` after
 * each click, the pager/rows reflecting the new segment, and the choice
 * surviving 30s (>= 3 `AutoRefresh` ticks at the 12s default).
 */
test.setTimeout(90_000);

test("T3.51: clicking a /lab segment tab changes ?state= and survives 3 AutoRefresh ticks", async ({ page }) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (e) => pageErrors.push(String(e).slice(0, 200)));

  await page.goto("/ever/lab", { waitUntil: "load", timeout: 60_000 });
  await page.waitForTimeout(2_000); // let hydration + the sidebar's own Link prefetches settle

  const tabs = page.getByRole("tab");
  console.log("URL0", page.url());
  console.log("tabs:", await tabs.allInnerTexts());
  console.log("selected0:", await tabs.evaluateAll((els) => els.map((e) => e.getAttribute("aria-selected"))));

  // --- click "Abertas" -------------------------------------------------
  await page.getByRole("tab", { name: /^Abertas/ }).click();
  await page.waitForURL(/[?&]state=open\b/, { timeout: 10_000 });
  console.log("URL1", page.url());
  await expect(page.getByRole("tab", { name: /^Abertas/ })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("tab", { name: /^Concluídas/ })).toHaveAttribute("aria-selected", "false");
  console.log("pager1:", await page.locator("p[aria-live]").last().innerText().catch(() => "n/a"));

  // --- click "Todas" -----------------------------------------------------
  await page.getByRole("tab", { name: /^Todas/ }).click();
  await page.waitForURL(/[?&]state=all\b/, { timeout: 10_000 });
  console.log("URL2", page.url());
  await expect(page.getByRole("tab", { name: /^Todas/ })).toHaveAttribute("aria-selected", "true");
  console.log("pager2:", await page.locator("p[aria-live]").last().innerText().catch(() => "n/a"));

  // --- 30s later (>= 3 AutoRefresh ticks at the 12s default): still "Todas" ---
  await page.waitForTimeout(30_000);
  console.log("URL3 (+30s)", page.url());
  expect(page.url()).toMatch(/[?&]state=all\b/);
  await expect(page.getByRole("tab", { name: /^Todas/ })).toHaveAttribute("aria-selected", "true");

  console.log("pageerrors:\n" + pageErrors.join("\n"));
});
