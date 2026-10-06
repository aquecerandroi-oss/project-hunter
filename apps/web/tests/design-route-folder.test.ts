// @vitest-environment node
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const appDir = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "app");

// Next.js App Router treats a folder starting with `_` as a PRIVATE folder:
// it is opted out of routing, so `app/_design/page.tsx` serves 404 in every
// environment (found 2026-10-06: commit 242a3591 renamed the folder from
// `%5Fdesign` to `_design`; the e2e job caught it only because dev and prod
// both answered 404). `%5F` is Next's documented escape for a literal
// underscore URL segment -- docs/DESIGN.md §4.
describe("/_design route folder", () => {
  it("uses the %5F escape so /_design is routable (not a private folder)", () => {
    expect(existsSync(path.join(appDir, "%5Fdesign", "page.tsx"))).toBe(true);
  });

  it("has no private `_design` folder shadowing it", () => {
    expect(existsSync(path.join(appDir, "_design"))).toBe(false);
  });
});
