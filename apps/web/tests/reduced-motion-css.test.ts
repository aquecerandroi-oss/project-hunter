import fs from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

/**
 * `prefers-reduced-motion` must neutralise transitions/animations app-wide
 * (M5, T1.5b fix pass), not just the price-flash keyframes -- before this
 * fix, `components/layout/sidebar.tsx`'s `transition-[width] duration-150`
 * (and anything else with its own transition/animation) kept animating for a
 * user who asked the OS for reduced motion. Parses the real, shipped
 * `app/globals.css` (same approach as `tests/theme-contrast.test.ts`) rather
 * than re-implementing the rule in the test.
 */
const CSS_PATH = path.join(__dirname, "..", "app", "globals.css");
const css = fs.readFileSync(CSS_PATH, "utf8");

function extractReducedMotionBlock(): string {
  const match = /@media \(prefers-reduced-motion: reduce\)\s*\{/.exec(css);
  if (!match) throw new Error("Could not find the @media (prefers-reduced-motion: reduce) block in app/globals.css");
  const start = match.index + match[0].length;
  let depth = 1;
  let i = start;
  while (depth > 0 && i < css.length) {
    if (css[i] === "{") depth++;
    if (css[i] === "}") depth--;
    i++;
  }
  return css.slice(start, i - 1);
}

describe("app/globals.css: prefers-reduced-motion neutralises transitions/animations app-wide (M5)", () => {
  const block = extractReducedMotionBlock();

  it("targets every element with the universal selector, not just the price-flash classes", () => {
    expect(block).toMatch(/\*\s*,\s*::before\s*,\s*::after\s*\{/);
  });

  it("forces both animation-duration and transition-duration to near-zero with !important", () => {
    expect(block).toMatch(/animation-duration:\s*0\.01ms\s*!important/);
    expect(block).toMatch(/transition-duration:\s*0\.01ms\s*!important/);
  });

  it("keeps the existing price-flash-specific gate alongside the new app-wide rule", () => {
    expect(block).toMatch(/\.flash-up\s*,\s*\.flash-down\s*\{\s*animation:\s*none;/);
  });
});
