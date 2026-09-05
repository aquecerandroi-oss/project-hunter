import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  vi.useRealTimers();
});

import { isPriceFlashEnabled, MIN_FLASH_INTERVAL_MS, setPriceFlashEnabled, usePriceFlash } from "@/hooks/usePriceFlash";

function setReducedMotion(matches: boolean): void {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches,
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  })) as unknown as typeof window.matchMedia;
}

beforeEach(() => {
  window.localStorage.clear();
  setReducedMotion(false);
});

describe("usePriceFlash: direction reflects the real change, and never fires on the first render", () => {
  it("stays null on mount (no previous value to compare against)", () => {
    const { result } = renderHook(({ value }) => usePriceFlash(value), { initialProps: { value: "100" } });
    expect(result.current).toBeNull();
  });

  it("flashes 'up' when the value increases", () => {
    const { result, rerender } = renderHook(({ value }) => usePriceFlash(value), { initialProps: { value: "100" } });
    rerender({ value: "101" });
    expect(result.current).toBe("up");
  });

  it("flashes 'down' when the value decreases", () => {
    const { result, rerender } = renderHook(({ value }) => usePriceFlash(value), { initialProps: { value: "100" } });
    rerender({ value: "99" });
    expect(result.current).toBe("down");
  });

  it("does not flash when the value is unchanged", () => {
    const { result, rerender } = renderHook(({ value }) => usePriceFlash(value), { initialProps: { value: "100" } });
    rerender({ value: "100" });
    expect(result.current).toBeNull();
  });

  it("clears the flash after FLASH_DURATION_MS", () => {
    vi.useFakeTimers();
    const { result, rerender } = renderHook(({ value }) => usePriceFlash(value), { initialProps: { value: "100" } });
    rerender({ value: "101" });
    expect(result.current).toBe("up");

    act(() => {
      vi.advanceTimersByTime(400);
    });

    expect(result.current).toBeNull();
  });
});

describe("usePriceFlash: a rate-limited (ignored) tick must never cancel the pending clear-flash timer (T1.5b Astra must-fix #5)", () => {
  it("still clears the flash on schedule even when a second tick arrives 50ms later and gets rate-limited", () => {
    vi.useFakeTimers();
    const { result, rerender } = renderHook(({ value }) => usePriceFlash(value), { initialProps: { value: "100" } });

    rerender({ value: "101" });
    expect(result.current).toBe("up");

    act(() => {
      vi.advanceTimersByTime(50);
    });
    rerender({ value: "102" }); // real change, but rate-limited (< MIN_FLASH_INTERVAL_MS since the last flash)
    expect(result.current).toBe("up"); // unaffected by the blocked tick

    act(() => {
      vi.advanceTimersByTime(400); // 450ms since the first flash -- well past FLASH_DURATION_MS (300ms)
    });

    expect(result.current).toBeNull();
  });
});

describe("usePriceFlash: calm by design -- rate limited, off switch, reduced-motion gated", () => {
  it("does not flash again within MIN_FLASH_INTERVAL_MS of the last flash (at most 1 per row per 2s)", () => {
    vi.useFakeTimers();
    const { result, rerender } = renderHook(({ value }) => usePriceFlash(value), { initialProps: { value: "100" } });
    rerender({ value: "101" });
    expect(result.current).toBe("up");

    act(() => {
      vi.advanceTimersByTime(300); // flash itself clears, but we're still inside the 2s window
    });
    rerender({ value: "102" });
    expect(result.current).toBeNull();

    act(() => {
      vi.advanceTimersByTime(MIN_FLASH_INTERVAL_MS);
    });
    rerender({ value: "103" });
    expect(result.current).toBe("up");
  });

  it("never flashes once the persisted setting is turned off", () => {
    setPriceFlashEnabled(false);
    expect(isPriceFlashEnabled()).toBe(false);

    const { result, rerender } = renderHook(({ value }) => usePriceFlash(value), { initialProps: { value: "100" } });
    rerender({ value: "150" });

    expect(result.current).toBeNull();
  });

  it("never flashes when prefers-reduced-motion is set, even with the setting on", () => {
    setPriceFlashEnabled(true);
    setReducedMotion(true);

    const { result, rerender } = renderHook(({ value }) => usePriceFlash(value), { initialProps: { value: "100" } });
    rerender({ value: "150" });

    expect(result.current).toBeNull();
  });
});

describe("usePriceFlash: a blocked Web Storage must never crash the row (NEW, Astra, T1.5b fix pass 2)", () => {
  it("falls back to the enabled default -- and never throws -- when localStorage.getItem throws SecurityError", () => {
    // Per the HTML Storage spec, `localStorage` access throws `SecurityError`
    // when storage is denied (Safari "block all cookies", managed-browser
    // policy, some private modes) -- before `lib/safe-storage.ts`, this threw
    // straight out of `isPriceFlashEnabled()`'s lazy `useState` initializer,
    // and since every row in the markets table calls this hook, the whole
    // table white-screened.
    const original = window.localStorage.getItem;
    window.localStorage.getItem = vi.fn(() => {
      throw new DOMException("blocked", "SecurityError");
    });

    try {
      expect(() => {
        const { result } = renderHook(({ value }) => usePriceFlash(value), { initialProps: { value: "100" } });
        expect(result.current).toBeNull(); // no flash on mount either way -- the point is it didn't throw
      }).not.toThrow();
    } finally {
      window.localStorage.getItem = original;
    }
  });

  it("does not throw when localStorage.setItem throws SecurityError while persisting the off switch", () => {
    const original = window.localStorage.setItem;
    window.localStorage.setItem = vi.fn(() => {
      throw new DOMException("blocked", "SecurityError");
    });

    try {
      expect(() => setPriceFlashEnabled(false)).not.toThrow();
    } finally {
      window.localStorage.setItem = original;
    }
  });
});
