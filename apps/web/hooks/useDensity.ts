"use client";

import { useEffect, useState } from "react";

/**
 * Table density (docs/DESIGN.md §2, joint decision #6: 40px rows standard,
 * 32px in compact). Reads the same `data-density` attribute
 * `components/settings/appearance-form.tsx` sets on `<html>` (and
 * `lib/pre-hydration-script.ts` applies before paint) -- one source of
 * truth for every density-aware layout, not a component-local guess.
 *
 * Mirrors `components/markets/candles-chart.tsx`'s `useThemeAttribute`
 * pattern: a `MutationObserver` on the one attribute is the only way a
 * component outside the toggle learns density changed in an already-open
 * tab.
 */
export type Density = "comfortable" | "compact";

export const ROW_HEIGHT_BY_DENSITY: Record<Density, number> = {
  comfortable: 40,
  compact: 32,
};

function readDensity(): Density {
  if (typeof document === "undefined") return "comfortable";
  return document.documentElement.getAttribute("data-density") === "compact" ? "compact" : "comfortable";
}

export function useDensity(): Density {
  // Fixed, SSR-safe default (H1, T1.5b fix pass): `readDensity()` used to
  // seed this `useState` directly, which is only "comfortable" on the server
  // (no `document`) but can read "compact" on the client the instant
  // `lib/pre-hydration-script.ts` has already set `data-density` before
  // React hydrates -- a structural hydration mismatch (28 vs 31 rendered
  // rows in `markets-table.tsx`'s virtualization) for any user who chose
  // "Compacta". Same fixed-default-then-`useEffect` pattern
  // `components/settings/appearance-form.tsx` already uses for its own
  // `density` field.
  const [density, setDensity] = useState<Density>("comfortable");

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- syncing from the DOM attribute, an external system, on mount
    setDensity(readDensity());
    const observer = new MutationObserver(() => setDensity(readDensity()));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-density"] });
    return () => observer.disconnect();
  }, []);

  return density;
}

/**
 * The single number a virtualized/table layout should size rows by --
 * `markets-table.tsx`'s row height, its windowing math AND its
 * `MarketRow`/header cell heights all read this same value, so the CSS and
 * the virtualization constant can never drift apart (docs/plans/M1.md's
 * joint decision: "hoje CSS e constante divergem").
 */
export function useRowHeight(): number {
  return ROW_HEIGHT_BY_DENSITY[useDensity()];
}
