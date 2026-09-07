import { clerkSetup } from "@clerk/testing/playwright";
import { expect, test } from "@playwright/test";

import { HAS_CLERK_E2E_KEYS, PUBLISHABLE_KEY, SECRET_KEY, signUpAndOnboard } from "./clerk-session";

/**
 * `/opportunities/[id]` and its "por que estamos olhando isso?" panel
 * (docs/plans/M2.md T2.8; `docs/reports/M2.md` calls this "o item mais forte do
 * M2"), against the **running local stack** — the episode under test is one the
 * scanner really scored, reached the way a trader reaches it: a click on a
 * radar row.
 *
 * **What this asserts and why each part matters.** The panel's whole job is
 * that every number on screen is traceable to the decomposition that produced
 * it, and that an absent component says *why* instead of rendering a bar at
 * zero (`components/opportunities/why-components.tsx`, Astra's T2.7 review,
 * must-fix 4). So the assertions are: the summary states score/confidence, the
 * component section renders at least one contribution bar whose accessible name
 * carries its own normalized value, every unavailable component carries a
 * machine-readable reason in parentheses, the anomalies/regime/feature sections
 * each land on one of their declared states, and the collapsed technical footer
 * really holds the versions and baseline ids.
 *
 * Gated exactly like `markets.spec.ts` (Clerk **test-mode** keys from the
 * environment; no credential is in this repository).
 */
test.describe("opportunity detail (docs/plans/M2.md T2.8)", () => {
  test.skip(!HAS_CLERK_E2E_KEYS, "CLERK_E2E keys not configured");

  test.beforeAll(async () => {
    if (!PUBLISHABLE_KEY || !SECRET_KEY) return;
    await clerkSetup({ publishableKey: PUBLISHABLE_KEY, secretKey: SECRET_KEY });
  });

  test("a radar row opens its episode and the why panel explains the score with components, anomalies, regime, features and a technical footer", async ({
    page,
  }) => {
    const orgSlug = await signUpAndOnboard(page, "opportunity");
    await page.goto(`/${orgSlug}/radar`);
    await expect(page.getByRole("heading", { name: "Radar", exact: true })).toBeVisible();

    const grid = page.getByRole("grid", { name: "Radar de oportunidades" });
    const empty = page.getByText("Nenhuma oportunidade pontuada ainda.");
    await expect(grid.or(empty).first()).toBeVisible({ timeout: 20_000 });
    if (!(await grid.isVisible())) {
      // Honest, named skip rather than a green test that asserted nothing: with
      // no scored episode there is no detail page to open. The write path that
      // creates one is proved against testcontainers in
      // `tests/integration/test_m2_pipeline.py`, not faked here.
      test.skip(
        true,
        "o stack local não tem episódio pontuado agora: nenhuma oportunidade para abrir",
      );
      return;
    }

    const firstRow = grid.getByRole("row").nth(1);
    const symbol = (await firstRow.getByRole("gridcell").nth(0).innerText()).split(/\s+/)[0];
    expect(symbol).toBeTruthy();

    // The score cell has no link in it, so clicking it hits the row's own
    // handler -- the navigation the product intends, not a URL typed by the test.
    await firstRow.getByRole("gridcell").nth(1).click();
    await page.waitForURL(new RegExp(`/${orgSlug}/opportunities/[0-9a-f-]{36}$`), {
      timeout: 15_000,
    });

    // ---- summary: score, "de 100", confidence, and the deterministic pt-BR
    // sentence the scoring engine wrote (never re-summarized by the UI).
    await expect(page.getByRole("heading", { name: new RegExp(`^${symbol}`) })).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByText("de 100", { exact: true })).toBeVisible();
    await expect(page.getByText(/^Confiança \d/)).toBeVisible();
    await expect(page.getByText(/^Score \d+,\d{2} de 100, confiança \d/)).toBeVisible();

    // ---- components: at least one real contribution bar, named with its own
    // number; and every unavailable one carries its machine-readable reason.
    const components = page.locator("section", {
      has: page.getByRole("heading", { name: "Componentes" }),
    });
    await expect(components).toBeVisible();
    await expect(
      components.getByText(
        "Decomposição em formato não reconhecido -- ver JSON bruto no rodapé técnico.",
      ),
    ).toHaveCount(0);
    await expect(components.getByRole("img", { name: /: \d+\.\d+ de 100$/ }).first()).toBeVisible();
    await expect(components.getByText(/^normalizado \d/).first()).toBeVisible();
    const withoutData = components.getByText(/^sem dado/);
    for (let index = 0; index < (await withoutData.count()); index += 1) {
      // "sem dado" alone would be the fabricated silence this panel exists to
      // prevent; the reason in parentheses is the contract.
      await expect(withoutData.nth(index)).toHaveText(/^sem dado \([a-z_]+\)$/);
    }

    // ---- anomalies and regime: each in one of its declared states.
    const context = page.locator("section", {
      has: page.getByRole("heading", { name: "Anomalias ativas" }),
    });
    await expect(context).toBeVisible();
    await expect(
      context
        .getByText("Nenhuma anomalia ativa ligada a este mercado.")
        .or(context.getByText(/severidade \d/).first())
        .first(),
    ).toBeVisible();
    await expect(context.getByRole("heading", { name: "Regime" })).toBeVisible();
    await expect(
      context
        .getByText("Nenhum regime vinculado a este episódio.")
        .or(context.getByText(/não confirmado na leitura atual/))
        .or(context.getByText(/^desde \d{4}-/))
        .first(),
    ).toBeVisible();

    // ---- feature snapshot: the compact table, or an honest reason for not
    // having one. Never an unrecognized-shape fallback.
    const features = page.locator("section", {
      has: page.getByRole("heading", { name: "Features", exact: true }),
    });
    await expect(features).toBeVisible();
    await expect(features.getByText(/formato não reconhecido/)).toHaveCount(0);
    await expect(
      features
        .getByRole("columnheader", { name: "Feature" })
        .or(features.getByText(/^Sem feature_snapshot/))
        .first(),
    ).toBeVisible();

    // ---- history + technical footer: collapsed by default, and it really
    // holds the versions and the baseline ids the score referenced.
    await expect(page.getByRole("heading", { name: /^Histórico do score/ })).toBeVisible();
    const footer = page.getByRole("group").filter({ has: page.getByText("Rodapé técnico") });
    await expect(page.getByText("weights_version")).toHaveCount(0);
    await footer.getByText("Rodapé técnico").click();
    await expect(page.getByText("weights_version")).toBeVisible();
    await expect(page.getByText(/^baseline_ids \(\d+\)$/)).toBeVisible();
  });
});
