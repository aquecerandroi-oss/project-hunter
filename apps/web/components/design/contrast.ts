/**
 * WCAG 2 contrast math shared by the design-tokens preview
 * (app/_design/page.tsx, dev-only). Deliberately independent from
 * tests/theme-contrast.test.ts -- that test parses app/globals.css directly
 * (the source of truth); this reads whatever the browser actually resolved
 * for the active theme via `getComputedStyle`, which is the right source
 * for a page whose whole point is showing what really rendered.
 */

function hexToRgb(hex: string): [number, number, number] | null {
  const h = hex.trim().replace("#", "");
  if (!/^[0-9a-fA-F]{6}$/.test(h)) return null;
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}

function linearize(channel: number): number {
  const s = channel / 255;
  return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
}

function relativeLuminance([r, g, b]: [number, number, number]): number {
  return 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b);
}

/** WCAG contrast ratio between two `#rrggbb` colors; `null` if either fails to parse. */
export function contrastRatio(hexA: string, hexB: string): number | null {
  const rgbA = hexToRgb(hexA);
  const rgbB = hexToRgb(hexB);
  if (!rgbA || !rgbB) return null;
  const lumA = relativeLuminance(rgbA);
  const lumB = relativeLuminance(rgbB);
  const [lighter, darker] = lumA > lumB ? [lumA, lumB] : [lumB, lumA];
  return (lighter + 0.05) / (darker + 0.05);
}

export const AA_NORMAL_TEXT = 4.5;

/**
 * Reads a `--color-*` custom property off `document.documentElement` as
 * resolved right now (i.e. whichever theme is currently applied). Browsers
 * normalize `getComputedStyle` color output to `rgb(...)`/`rgba(...)`, not
 * the `#hex` the CSS literally wrote -- convert so `contrastRatio` (and the
 * on-screen hex label) have one consistent format.
 */
export function readColorToken(name: string): string {
  const raw = getComputedStyle(document.documentElement).getPropertyValue(`--color-${name}`).trim();
  const rgbMatch = /^rgba?\((\d+),\s*(\d+),\s*(\d+)/.exec(raw);
  if (rgbMatch) {
    const [, r, g, b] = rgbMatch;
    return (
      "#" +
      [r, g, b]
        .map((v) => Number(v).toString(16).padStart(2, "0"))
        .join("")
    );
  }
  return raw;
}
