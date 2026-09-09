import { expect, test } from "@playwright/test";

/**
 * T3.49 -- Everton (2026-09-08 19:45/19:50): "quero conferir visualmente se
 * a linha estava certa". Descartável (não é `*.spec.ts`; roda via
 * `lab-trendline-overlay.config.ts`, mesmo padrão de
 * `lab-tabs-click.audit.ts`/`design-audit.audit.ts`).
 *
 * Dado real, local (nunca a VPS): `trendline_breakout v1` foi ativada no
 * stack local (`docker compose run --rm ops python
 * infra/scripts/activate_strategy_version.py trendline_breakout v1 ...`,
 * mesmo digest `...7b83a1ff...` da VPS) e um replay real rodou
 * (`docker compose run --rm ops python -m hunter_strategy_worker.replay.run
 * --version trendline_breakout:v1 --from 2026-08-15 --to 2026-09-08
 * --markets BTCUSDT,ETHUSDT,SOLUSDT --workers 3`), cohort
 * `replay:da63e72d-2e29-4e7e-88ef-fe2ed1dbd0ea`, 27 sinais reais, 0 erros.
 * O sinal aberto aqui é ETHUSDT, barra de decisão `2026-08-20T12:15:00Z`,
 * resultado `target` (lido direto do banco antes deste spec).
 */
test.setTimeout(90_000);

const COHORT = "replay:da63e72d-2e29-4e7e-88ef-fe2ed1dbd0ea";
const VERSION_ID = "01a0836d-cdb9-7056-b061-c6f1b6f6c6d9";

test("T3.49: abre o detalhe de uma operação real de trendline_breakout v1 e desenha a linha", async ({ page }) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (e) => pageErrors.push(String(e).slice(0, 300)));

  await page.goto(`/ever/lab?cohort=${encodeURIComponent(COHORT)}&version=${VERSION_ID}&state=all&page_size=500`, {
    waitUntil: "load",
    timeout: 60_000,
  });
  await page.waitForTimeout(2_000);

  console.log("URL", page.url());
  console.log("rows found:", await page.getByRole("row").count());

  const row = page.locator('[role="row"]', { has: page.locator('[title*="2026-08-20T12:15"]') });
  await expect(row).toHaveCount(1);
  await row.click();

  await expect(page.getByText(/Decisão:/)).toBeVisible();

  const button = page.getByRole("button", { name: "Ver linha de tendência" });
  await expect(button).toBeVisible();
  await button.click();

  await expect(page.getByText("Geometria da linha")).toBeVisible({ timeout: 20_000 });
  console.log("aviso de derivação (1m->15m):", await page.getByText(/Candles agregadas de 1m real/).count());
  console.log("notas honestas do overlay:", await page.locator("li", { hasText: "não desenhad" }).allInnerTexts().catch(() => []));

  await page.screenshot({ path: "../../.claude/state/design/2026-09-08/t3.49-lab-trendline-1440-dark.png", fullPage: true });

  await page.getByRole("button", { name: "Alternar tema" }).click();
  await page.waitForTimeout(500);
  await page.screenshot({ path: "../../.claude/state/design/2026-09-08/t3.49-lab-trendline-1440-light.png", fullPage: true });

  console.log("pageerrors:\n" + pageErrors.join("\n"));
  expect(pageErrors.filter((e) => e.includes("Value is null"))).toHaveLength(0);
});
