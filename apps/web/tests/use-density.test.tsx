import { act, cleanup, render, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

afterEach(() => {
  cleanup();
  document.documentElement.removeAttribute("data-density");
});

import { ROW_HEIGHT_BY_DENSITY, useDensity, useRowHeight } from "@/hooks/useDensity";

describe("useDensity / useRowHeight: one source of truth for row height (T1.5b joint decision #6)", () => {
  it("defaults to comfortable (40px) with no data-density attribute set", () => {
    const { result } = renderHook(() => useRowHeight());
    expect(result.current).toBe(ROW_HEIGHT_BY_DENSITY.comfortable);
    expect(result.current).toBe(40);
  });

  it("reads compact (32px) from an existing data-density attribute at mount", () => {
    document.documentElement.setAttribute("data-density", "compact");
    const { result } = renderHook(() => useRowHeight());
    expect(result.current).toBe(32);
  });

  it("reacts live to data-density changing in an already-mounted tab (mirrors the theme MutationObserver pattern)", async () => {
    const { result } = renderHook(() => useDensity());
    expect(result.current).toBe("comfortable");

    // jsdom's MutationObserver notifies asynchronously (a microtask), same
    // as `candles-chart.test.tsx`'s theme-attribute test -- `act()` around
    // the attribute change alone is not enough, `waitFor` lets that
    // microtask actually run before the assertion.
    act(() => {
      document.documentElement.setAttribute("data-density", "compact");
    });

    await waitFor(() => expect(result.current).toBe("compact"));
  });

  it("never diverges: the CSS-facing constant map has exactly comfortable=40 and compact=32", () => {
    expect(ROW_HEIGHT_BY_DENSITY).toEqual({ comfortable: 40, compact: 32 });
  });
});

describe("useDensity: SSR-safe default, corrected after mount (H1, T1.5b fix pass)", () => {
  it("renders 'comfortable' on the very first render even when data-density is already 'compact' on <html>, then settles on 'compact'", async () => {
    // Mirrors production: `lib/pre-hydration-script.ts` sets `data-density`
    // on `<html>` before React hydrates, so a naive `useState(readDensity)`
    // would read "compact" synchronously at mount -- a value the server
    // could never have produced (no `document` there) and a structural
    // hydration mismatch in any density-aware virtualized table.
    document.documentElement.setAttribute("data-density", "compact");

    const renders: string[] = [];
    function Probe() {
      const density = useDensity();
      renders.push(density);
      return null;
    }

    render(<Probe />);

    expect(renders[0]).toBe("comfortable");
    await waitFor(() => expect(renders[renders.length - 1]).toBe("compact"));
  });
});
