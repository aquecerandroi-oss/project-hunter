import { logger } from "@/lib/logger";

/**
 * T3.31 -- "Error: Value is null" audit (`.claude/state/notes-T3.31.md`)
 * traced the crash to `lightweight-charts` internals, not to this function
 * directly; this guard exists anyway because `candles-chart.tsx`,
 * `portfolio-equity-chart.tsx` and `lab-curve-chart.tsx` each used to read
 * `getComputedStyle` inline with no fallback -- a token renamed/removed from
 * `app/globals.css` (docs/DESIGN.md §1) would silently hand
 * `lightweight-charts` `color: ""`/`textColor: ""` instead of failing loud.
 * `fallback` is a literal hex (never another token name, so a broken lookup
 * can never recurse into a second broken lookup) -- callers pass the current
 * dark-theme value of the same token from `app/globals.css` as their safety
 * net. Warns once per token name (not once per call/render) so a genuinely
 * missing token is visible in the logs without spamming them on every paint.
 */
const warnedTokens = new Set<string>();

export function cssVar(name: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  if (value !== "") return value;
  if (!warnedTokens.has(name)) {
    warnedTokens.add(name);
    logger.warn("chart_css_var_missing", { name, fallback });
  }
  return fallback;
}

/**
 * The dark-theme value of every token the three chart components read
 * (`app/globals.css`'s `@theme` -- keep in sync with it, docs/DESIGN.md §1),
 * used only as `cssVar`'s last-resort fallback. `"#a3a3a3"` (`fg-muted`) is
 * the default for any token not listed here -- a neutral grey is always a
 * safe stand-in for a line/border/text colour.
 */
const CHART_TOKEN_FALLBACK: Record<string, string> = {
  "--color-border": "#232323",
  "--color-fg-muted": "#a3a3a3",
  "--color-green": "#22c55e",
  "--color-red": "#ef4444",
  "--color-info": "#60a5fa",
  "--color-warning": "#f59e0b",
};

/** `cssVar` with the fallback looked up from `CHART_TOKEN_FALLBACK` -- the call-site shorthand every chart component uses. */
export function chartColor(name: string): string {
  return cssVar(name, CHART_TOKEN_FALLBACK[name] ?? "#a3a3a3");
}
