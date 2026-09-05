"use client";

import { useEffect, useState } from "react";

/**
 * `prefers-reduced-motion` (CLAUDE.md, docs/DESIGN.md §2, joint decision #4)
 * -- every animated affordance in the app (price flash, shimmer, status
 * transitions) must gate on this, not just on the user's own opt-out
 * setting below. `matchMedia` is unavailable during SSR, so the initial
 * render assumes motion is fine (the common case) and corrects itself on
 * mount, same trade-off `ThemeToggle` already accepts for `data-theme`.
 */
function readPrefersReducedMotion(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function usePrefersReducedMotion(): boolean {
  // Fixed, SSR-safe default (nice-to-have, T1.5b fix pass 2 #4): the previous
  // `useState(readPrefersReducedMotion)` called `matchMedia` directly inside
  // the initializer, so the server always started `false` but a browser that
  // already prefers reduced motion started `true` on its very first render --
  // the same class of hydration mismatch `useDensity`/`AppearanceForm`'s
  // `priceFlash` field already had to fix (H1/M1). Corrected in the mount
  // effect below instead, same fixed-default-then-effect pattern.
  const [reduced, setReduced] = useState<boolean>(false);

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return undefined;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- syncing from matchMedia, an external system, once mounted
    setReduced(readPrefersReducedMotion());
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const listener = (event: MediaQueryListEvent) => setReduced(event.matches);
    query.addEventListener("change", listener);
    return () => query.removeEventListener("change", listener);
  }, []);

  return reduced;
}
