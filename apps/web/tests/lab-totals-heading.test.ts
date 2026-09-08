import { describe, expect, it } from "vitest";

import { totalsHeading } from "@/components/lab/lab-totals-heading";

/** Split out of `lab-money.test.ts` alongside `lab-totals-heading.ts` (brief T3.38) to keep both files under the lint config's 350-line budget. */
describe("totalsHeading: the card's own scope-switch wording (brief T3.37, replacing the old hasMore inference; extended by T3.38 item 3)", () => {
  it("says 'desta página' with the loaded page's own count in the 'page' scope, single-version (no duplicates possible)", () => {
    expect(totalsHeading("page", { uniqueCount: 200, rowCount: 200, versionsMixed: false }, 2135)).toBe(
      "Resultado das operações desta página (200)",
    );
  });

  it("says 'todas as operações concluídas' with the real closed total in the 'allClosed' scope, ignoring the page's own count", () => {
    expect(totalsHeading("allClosed", { uniqueCount: 200, rowCount: 200, versionsMixed: false }, 2135)).toBe(
      "Resultado de todas as operações concluídas (2135)",
    );
  });

  it("never says 'há mais sinais além desta página' (Everton's screenshot, item 1: that read as if it were the Lab's whole total)", () => {
    expect(totalsHeading("page", { uniqueCount: 200, rowCount: 200, versionsMixed: false }, 2135)).not.toMatch(/há mais sinais/);
  });

  it("spells out 'N únicas de M linhas' once the page mixes versions (brief T3.38, RAYSOLUSDT screenshot: three rows, one real operation)", () => {
    expect(totalsHeading("page", { uniqueCount: 1, rowCount: 3, versionsMixed: true }, 2135)).toBe(
      "Resultado das operações desta página (1 única de 3 linhas)",
    );
  });

  it("still spells out both counts when versionsMixed even without an actual duplicate on this page (equal counts, honest either way)", () => {
    expect(totalsHeading("page", { uniqueCount: 2, rowCount: 2, versionsMixed: true }, 2135)).toBe(
      "Resultado das operações desta página (2 únicas de 2 linhas)",
    );
  });
});
