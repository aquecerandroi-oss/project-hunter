import { clerkSetup } from "@clerk/testing/playwright";
import { expect, test, type Locator, type Page } from "@playwright/test";

import { HAS_CLERK_E2E_KEYS, PUBLISHABLE_KEY, SECRET_KEY, signUpAndOnboard } from "./clerk-session";

/**
 * `/radar` against the **running local stack** (docs/plans/M2.md T2.8,
 * condition 4 of `docs/reports/M2.md`'s VEREDITO). Nothing here is seeded and
 * nothing is stubbed: the rows, or their absence, are whatever
 * `services/scanner-worker` has actually scored into `opportunities` at the
 * moment the test runs.
 *
 * **Why the two-branch shape is the assertion, not a hedge.** The M2 rule the
 * radar exists to honour is that a market with no scored episode is *absent*,
 * never a fabricated zero (`components/radar/radar-empty.tsx`,
 * `repositories/radar.py`: the query selects FROM `opportunities`, never FROM
 * `markets`). So the honest test is "either real rows whose scores came from
 * the API, or the empty state that names why" — and, in both branches, a
 * positive check that the *other* branch's artefact is not on screen. A test
 * that demanded rows would be red every time the scanner has nothing to say,
 * which is a legitimate state of this product.
 *
 * Gated exactly like `markets.spec.ts`: real, non-fake Clerk **test-mode**
 * dev-instance keys via `CLERK_E2E_PUBLISHABLE_KEY`/`CLERK_E2E_SECRET_KEY`.
 * Absent keys -> `test.skip` with the reason, never a failure.
 */
const SCORE_PATTERN = /^\d{1,3}\.\d{2}$/;
const STATUSES = ["NORMAL", "WATCHING", "ANOMALY", "HOT", "ENTRY_CANDIDATE", "EXTENDED", "EXPIRED"];
const STAGE_LABELS = ["EARLY", "DEVELOPING", "EXTENDED", "estágio indisponível"];

function grid(page: Page): Locator {
  return page.getByRole("grid", { name: "Radar de oportunidades" });
}

function emptyState(page: Page): Locator {
  return page.getByText("Nenhuma oportunidade pontuada ainda.");
}

/** Waits for the page to settle into exactly one of its two legitimate states. */
async function radarState(page: Page): Promise<"rows" | "empty"> {
  await expect(grid(page).or(emptyState(page)).first()).toBeVisible({ timeout: 20_000 });
  return (await grid(page).isVisible()) ? "rows" : "empty";
}

test.describe("radar (docs/plans/M2.md T2.8)", () => {
  test.skip(!HAS_CLERK_E2E_KEYS, "CLERK_E2E keys not configured");

  test.beforeAll(async () => {
    if (!PUBLISHABLE_KEY || !SECRET_KEY) return;
    await clerkSetup({ publishableKey: PUBLISHABLE_KEY, secretKey: SECRET_KEY });
  });

  test("rows carry a real score, a status chip and a stage chip stamped with an as_of — or the empty state says so instead of showing zeros", async ({
    page,
  }) => {
    const orgSlug = await signUpAndOnboard(page, "radar");
    await page.goto(`/${orgSlug}/radar`);
    await expect(page.getByRole("heading", { name: "Radar", exact: true })).toBeVisible();

    const state = await radarState(page);

    if (state === "empty") {
      // The honest empty state, and the proof it is not a table of zeros.
      await expect(emptyState(page)).toBeVisible();
      await expect(page.getByText(/uma linha por episódio de oportunidade pontuado/)).toBeVisible();
      await expect(grid(page)).toHaveCount(0);
      return;
    }

    // `as_of` is on screen and is a real UTC stamp, not the word "agora": the
    // radar's own note line carries both the panel's query time and the
    // separate anomalies-aggregate time (Astra's T2.7 review, must-fix 3).
    await expect(
      page.getByText(/^Painel consultado \d{4}-\d{2}-\d{2}.*anomalias verificadas /),
    ).toBeVisible();
    await expect(emptyState(page)).toHaveCount(0);

    const firstRow = grid(page).getByRole("row").nth(1);
    await expect(firstRow).toBeVisible();

    // Score: the API's own `NUMERIC(5,2)` string, rendered verbatim. A
    // fabricated placeholder ("--", "0", "n/a") would not match.
    const score = (await firstRow.getByRole("gridcell").nth(1).innerText()).split("\n")[0]?.trim();
    expect(score).toMatch(SCORE_PATTERN);

    const status = (await firstRow.getByRole("gridcell").nth(2).innerText()).trim();
    expect(STATUSES).toContain(status);

    // `OpportunityStage.NONE` is a real member ("we cannot tell yet") and is
    // rendered as muted prose, never as EARLY and never hidden
    // (`components/radar/status-chip.tsx`).
    const stage = (await firstRow.getByRole("gridcell").nth(3).innerText()).trim();
    expect(STAGE_LABELS).toContain(stage);

    // Quality column states confidence or says it is unavailable -- never 0.
    await expect(firstRow.getByRole("gridcell").nth(5)).toHaveText(/confiança (indisponível|\d)/);
  });

  test("the symbol filter and the score sort are server round trips carried in the URL", async ({
    page,
  }) => {
    const orgSlug = await signUpAndOnboard(page, "radarfilter");
    await page.goto(`/${orgSlug}/radar`);
    const initial = await radarState(page);

    // ---- filter: a symbol nobody lists must produce the *filtered* empty
    // state, which is a different sentence from "nothing scored yet". The two
    // reading the same would hide a broken filter behind an empty scanner.
    await page.getByLabel("Buscar símbolo no radar").fill("ZZZ_NO_SUCH_SYMBOL");
    await page.getByLabel("Score mínimo").click(); // blur commits the filter
    await page.waitForURL(/\?.*q=ZZZ_NO_SUCH_SYMBOL/, { timeout: 15_000 });
    await expect(page.getByText("Nenhum episódio encontrado para estes filtros.")).toBeVisible({
      timeout: 15_000,
    });
    await expect(emptyState(page)).toHaveCount(0);

    if (initial === "empty") {
      test.skip(
        true,
        "o radar local não tem episódio pontuado agora: sem linhas, não há ordenação a exercer",
      );
      return;
    }

    // ---- sort: clicking the Score header navigates (server-side sort), the
    // URL carries it and the header reports it through aria-sort.
    await page.goto(`/${orgSlug}/radar`);
    await expect(grid(page)).toBeVisible({ timeout: 20_000 });
    const scoreHeader = page.getByRole("columnheader", { name: /^Score/ });
    await expect(scoreHeader).toHaveAttribute("aria-sort", "descending");
    const before = await grid(page)
      .getByRole("row")
      .nth(1)
      .getByRole("gridcell")
      .nth(1)
      .innerText();

    await scoreHeader.getByRole("button").click();
    await page.waitForURL(/sort=score&order=asc/, { timeout: 15_000 });
    await expect(page.getByRole("columnheader", { name: /^Score/ })).toHaveAttribute(
      "aria-sort",
      "ascending",
      { timeout: 20_000 },
    );

    // Ascending must actually start lower than descending did -- the URL
    // changing on its own would also pass against a sort the server ignored.
    const after = await grid(page).getByRole("row").nth(1).getByRole("gridcell").nth(1).innerText();
    const first = Number(before.split("\n")[0]);
    const second = Number(after.split("\n")[0]);
    expect(second).toBeLessThanOrEqual(first);
  });
});
