import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(cleanup);

import { MotionShowcase } from "@/components/design/motion-showcase";
import { usePrefersReducedMotion } from "@/hooks/usePrefersReducedMotion";

beforeEach(() => {
  window.localStorage.clear();
});

describe("MotionShowcase: price-flash toggle has a fixed SSR-safe default, corrected after mount (M1, T1.5b fix pass)", () => {
  it("reads an already-persisted 'off' setting after mount, not just the fixed 'ligado' default", () => {
    window.localStorage.setItem("hunter-price-flash-enabled", "off");
    render(<MotionShowcase />);

    // A lazy `useState(isPriceFlashEnabled)` initializer would read
    // `localStorage` directly at construction time -- fine in this
    // synchronous jsdom render, but the same pattern is what caused a real
    // SSR/hydration mismatch in `appearance-form.tsx`'s sibling field. This
    // asserts the corrected (fixed-default + effect) implementation still
    // ends up reflecting the persisted value once mounted.
    expect(screen.getByRole("button", { name: /Flash: desligado/ })).toBeInTheDocument();
  });

  it("defaults to 'ligado' with nothing persisted", () => {
    render(<MotionShowcase />);
    expect(screen.getByRole("button", { name: /Flash: ligado/ })).toBeInTheDocument();
  });
});

describe("usePrefersReducedMotion (used by MotionShowcase, docs/DESIGN.md §2): SSR-safe default, corrected after mount (nice-to-have, T1.5b fix pass 2 #4)", () => {
  afterEach(() => {
    // @ts-expect-error -- jsdom has no matchMedia by default; undo the per-test stub below.
    delete window.matchMedia;
  });

  it("renders false on the very first render even when the OS already prefers reduced motion, then settles on true", async () => {
    // `readPrefersReducedMotion()` calling `matchMedia` directly inside the
    // `useState` initializer (the old bug -- same class as H1/M1) would make
    // THIS render's very first pass already read `true`, which is exactly
    // what the old version of this test (asserting only the post-effect
    // state) could never catch (Astra's review). A `Probe` that records
    // every render's value -- same technique `tests/use-density.test.tsx`
    // uses for the identical bug class -- exposes the pre-effect value too.
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: true,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })) as unknown as typeof window.matchMedia;

    const renders: boolean[] = [];
    function Probe() {
      const reduced = usePrefersReducedMotion();
      renders.push(reduced);
      return null;
    }

    render(<Probe />);

    expect(renders[0]).toBe(false);
    await waitFor(() => expect(renders[renders.length - 1]).toBe(true));
  });
});
