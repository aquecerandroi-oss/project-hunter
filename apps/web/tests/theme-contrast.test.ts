import fs from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

/**
 * Parses the dark and light token tables straight out of `app/globals.css`
 * (the single source of truth per docs/DESIGN.md §1) and asserts WCAG AA
 * (>= 4.5:1) for every text/background pair docs/DESIGN.md calls out.
 *
 * Deliberately does not import a `lib/theme-tokens.ts` -- Tailwind 4 reads
 * `@theme` directly out of this CSS file, so the CSS itself has to stay the
 * source Tailwind consumes; parsing it here (instead of hand-copying hex
 * values into the test) is what keeps this test unable to drift from the
 * real, shipped tokens.
 */
const CSS_PATH = path.join(__dirname, "..", "app", "globals.css");
const css = fs.readFileSync(CSS_PATH, "utf8");

function extractBlock(css: string, selectorPattern: RegExp): string {
  const match = selectorPattern.exec(css);
  if (!match) throw new Error(`Could not find block for ${selectorPattern}`);
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

function parseTokens(block: string): Record<string, string> {
  const tokens: Record<string, string> = {};
  const re = /--color-([a-z0-9-]+):\s*(#[0-9a-fA-F]{3,8})\s*;/g;
  for (const m of block.matchAll(re)) {
    const name = m[1];
    const hex = m[2];
    if (name && hex) tokens[name] = hex.toLowerCase();
  }
  return tokens;
}

/** Looks up a token, failing with a clear message instead of returning `undefined` (noUncheckedIndexedAccess). */
function token(tokens: Record<string, string>, name: string): string {
  const value = tokens[name];
  if (!value) throw new Error(`Token --color-${name} was not parsed out of app/globals.css`);
  return value;
}

// Dark tokens live directly in the top-level `@theme { ... }` block.
const themeBlock = extractBlock(css, /@theme\s*\{/);
const darkTokens = parseTokens(themeBlock);

// Light tokens live in the `.light, [data-theme="light"] { ... }` block and
// only override a subset -- merge over the dark tokens for the ones that
// don't change (border/warning/info aren't overridden, so re-checking with
// the dark value would be wrong; every pair asserted below IS overridden).
const lightBlock = extractBlock(css, /\[data-theme="light"\]\s*\{/);
const lightTokens = { ...darkTokens, ...parseTokens(lightBlock) };

function hexToRgb(hex: string): [number, number, number] {
  let h = hex.replace("#", "");
  if (h.length === 3) {
    h = h
      .split("")
      .map((c) => c + c)
      .join("");
  }
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return [r, g, b];
}

function linearize(channel: number): number {
  const s = channel / 255;
  return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
}

function relativeLuminance(hex: string): number {
  const [r, g, b] = hexToRgb(hex);
  return 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b);
}

/** WCAG 2 contrast ratio between two colors, order-independent. */
function contrastRatio(hexA: string, hexB: string): number {
  const lumA = relativeLuminance(hexA);
  const lumB = relativeLuminance(hexB);
  const [lighter, darker] = lumA > lumB ? [lumA, lumB] : [lumB, lumA];
  return (lighter + 0.05) / (darker + 0.05);
}

const AA_NORMAL_TEXT = 4.5;

describe("theme tokens parsed from app/globals.css", () => {
  it("dark theme defines every token docs/DESIGN.md §1 requires", () => {
    for (const key of [
      "bg",
      "bg-elevated",
      "bg-overlay",
      "border",
      "border-strong",
      "fg",
      "fg-muted",
      "fg-subtle",
      "gold",
      "gold-strong",
      "gold-soft",
      "gold-fg",
      "green",
      "green-soft",
      "red",
      "red-soft",
      "warning",
      "info",
    ]) {
      expect(darkTokens[key], `missing dark --color-${key}`).toBeDefined();
    }
  });

  it("light theme overrides every non-decorative token", () => {
    for (const key of [
      "bg",
      "bg-elevated",
      "bg-overlay",
      "border",
      "border-strong",
      "fg",
      "fg-muted",
      "fg-subtle",
      "gold",
      "gold-strong",
      "gold-soft",
      "gold-fg",
      "green",
      "green-soft",
      "red",
      "red-soft",
      "warning",
      "info",
    ]) {
      expect(lightTokens[key], `missing light --color-${key}`).toBeDefined();
    }
  });

  describe.each([
    ["dark", darkTokens],
    ["light", lightTokens],
  ] as const)("%s theme -- WCAG AA (>= 4.5:1)", (_name, tokens) => {
    it("fg on bg", () => {
      expect(contrastRatio(token(tokens, "fg"), token(tokens, "bg"))).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
    });

    it("fg on bg-elevated", () => {
      expect(contrastRatio(token(tokens, "fg"), token(tokens, "bg-elevated"))).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
    });

    it("fg-muted on bg", () => {
      expect(contrastRatio(token(tokens, "fg-muted"), token(tokens, "bg"))).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
    });

    // T1.5b joint decision #9: "contraste >= 4.5:1 também para fg-subtle
    // onde carrega informação" -- it labels ages, exchange codes and
    // snapshot timestamps (DESIGN-2, docs/DESIGN.md §5), not just decorative
    // placeholders, so it must clear AA like every other informational token.
    it("fg-subtle on bg", () => {
      expect(contrastRatio(token(tokens, "fg-subtle"), token(tokens, "bg"))).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
    });

    it("fg-subtle on bg-elevated", () => {
      expect(contrastRatio(token(tokens, "fg-subtle"), token(tokens, "bg-elevated"))).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
    });

    // M6 (T1.5b fix pass): the contrast net only checked `fg-subtle` over
    // `bg`/`bg-elevated` -- extended to the backgrounds these tokens are
    // actually used on in this diff: `bg-overlay` (the sticky table header,
    // hover rows, the command palette's own surface) and `gold-soft` (the
    // command palette's SELECTED result row, `components/layout/
    // command-palette.tsx`, which renders `fg-muted` for the exchange code).
    it("fg-subtle on bg-overlay", () => {
      expect(contrastRatio(token(tokens, "fg-subtle"), token(tokens, "bg-overlay"))).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
    });

    it("fg-muted on bg-overlay", () => {
      expect(contrastRatio(token(tokens, "fg-muted"), token(tokens, "bg-overlay"))).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
    });

    it("fg-muted on gold-soft (command palette's selected result row)", () => {
      expect(contrastRatio(token(tokens, "fg-muted"), token(tokens, "gold-soft"))).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
    });

    it("gold-fg on gold", () => {
      expect(contrastRatio(token(tokens, "gold-fg"), token(tokens, "gold"))).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
    });

    it("green on bg", () => {
      expect(contrastRatio(token(tokens, "green"), token(tokens, "bg"))).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
    });

    it("red on bg", () => {
      expect(contrastRatio(token(tokens, "red"), token(tokens, "bg"))).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
    });

    it("gold on bg", () => {
      expect(contrastRatio(token(tokens, "gold"), token(tokens, "bg"))).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
    });
  });

  it("light gold on white (the page background) is >= 4.5:1", () => {
    expect(contrastRatio(token(lightTokens, "gold"), "#ffffff")).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
  });
});
