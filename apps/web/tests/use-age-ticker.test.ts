import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

import { computeAgeMs, heartbeatServerNowIso, useAgeTicker, useServerClock } from "@/hooks/useAgeTicker";

describe("useServerClock: offset = serverNow - receivedAt (T3.16)", () => {
  it("returns null when there is no server_now to anchor on", () => {
    const { result } = renderHook(() => useServerClock(null, Date.now()));
    expect(result.current).toBeNull();
  });

  it("returns null for an unparseable server_now instead of NaN", () => {
    const { result } = renderHook(() => useServerClock("not-a-date", Date.now()));
    expect(result.current).toBeNull();
  });

  it("computes a real offset from a valid server_now and receivedAt pair", () => {
    const receivedAt = 1_000_000;
    const serverNow = new Date(receivedAt + 5_000).toISOString(); // server clock 5s ahead of receivedAt
    const { result } = renderHook(() => useServerClock(serverNow, receivedAt));
    expect(result.current).toBe(5_000);
  });
});

describe("useAgeTicker: a viewer clock skew never changes `now` once server_now is present (T3.16 symptom, 2026-09-08 -- a viewer ~60s ahead turned every fresh row 'atrasado 1min')", () => {
  /**
   * The environment's `Date.now()` plays the viewer's own (skewed) clock
   * throughout -- `serverNowIso` is built from `trueNow` directly, never
   * from `Date.now()`, so it stays the honest, unskewed instant the API
   * would have reported. The bias stays constant across the whole test
   * (never reset mid-test) — a wall clock's skew from true UTC is a fixed
   * bias, not something that jumps around on its own.
   */
  function withSkewedViewerClock(trueNow: Date, skewMs: number): { serverNowIso: string } {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(trueNow.getTime() + skewMs));
    return { serverNowIso: trueNow.toISOString() };
  }

  it("a viewer clock 5 minutes ahead never inflates the computed age (matches the VPS symptom exactly)", () => {
    const trueNow = new Date("2026-09-08T03:50:00.000Z");
    const { serverNowIso } = withSkewedViewerClock(trueNow, 5 * 60_000);
    const tickerTs = trueNow.toISOString(); // a component that is genuinely fresh (age 0) on the real/server clock

    const { result } = renderHook(() => useAgeTicker(serverNowIso));

    expect(result.current.hasServerClock).toBe(true);
    // The skew cancels out: `now` reads the true instant, not the viewer's
    // biased one -- a naive `Date.now() - tickerTs` here would read ~5min.
    expect(result.current.now).toBe(trueNow.getTime());
    expect(computeAgeMs(tickerTs, result.current.now)).toBe(0);
  });

  it("a viewer clock 5 minutes behind never hides genuine staleness", () => {
    const trueNow = new Date("2026-09-08T03:50:00.000Z");
    const { serverNowIso } = withSkewedViewerClock(trueNow, -5 * 60_000);
    // A component that went quiet 20s ago on the real/server clock -- a
    // naive `Date.now() - tickerTs` (viewer 5min behind) would read negative
    // (clamped to 0 by `computeAgeMs`), hiding the real staleness.
    const tickerTs = new Date(trueNow.getTime() - 20_000).toISOString();

    const { result } = renderHook(() => useAgeTicker(serverNowIso));

    expect(result.current.now).toBe(trueNow.getTime());
    expect(computeAgeMs(tickerTs, result.current.now)).toBe(20_000);
  });

  it("real elapsed time still advances the age correctly under a constant viewer skew", () => {
    const trueNow = new Date("2026-09-08T03:50:00.000Z");
    const { serverNowIso } = withSkewedViewerClock(trueNow, 5 * 60_000);
    const tickerTs = trueNow.toISOString();

    const { result } = renderHook(() => useAgeTicker(serverNowIso));
    expect(computeAgeMs(tickerTs, result.current.now)).toBe(0);

    act(() => {
      vi.advanceTimersByTime(10_000); // 10s really pass; the fixed skew is untouched
    });

    // Exactly the real 10s elapsed -- never 10s plus the skew, never frozen.
    expect(computeAgeMs(tickerTs, result.current.now)).toBe(10_000);
  });

  it("falls back to the viewer's own clock (hasServerClock: false) when server_now is missing", () => {
    vi.useFakeTimers();
    const now = new Date("2026-09-08T03:50:00.000Z");
    vi.setSystemTime(now);

    const { result } = renderHook(() => useAgeTicker(null));
    expect(result.current.hasServerClock).toBe(false);
    expect(result.current.now).toBe(now.getTime());
  });

  it("re-anchors the offset when a fresh response's server_now arrives (a realtime/refetch tick)", () => {
    vi.useFakeTimers();
    const t0 = new Date("2026-09-08T03:50:00.000Z");
    vi.setSystemTime(t0);

    const { result, rerender } = renderHook(({ iso }) => useAgeTicker(iso), {
      initialProps: { iso: t0.toISOString() },
    });
    expect(result.current.hasServerClock).toBe(true);
    expect(result.current.now).toBe(t0.getTime());

    // Time really passes, and a fresh fetch delivers a new, later server_now.
    const t1 = new Date(t0.getTime() + 30_000);
    act(() => {
      vi.setSystemTime(t1);
    });
    rerender({ iso: t1.toISOString() });
    // The re-anchoring effect (a `useEffect`, not render) needs one tick to
    // commit before the ticking clock below reads the fresh anchor.
    act(() => {
      vi.advanceTimersByTime(1_000);
    });

    // A component fresh as of `t1` (the new response) must read as fresh
    // (age ~0, never ~30s) -- proof the offset actually re-anchored to the
    // new response instead of staying pinned to `t0`'s.
    const freshTickerTs = t1.toISOString();
    expect(computeAgeMs(freshTickerTs, result.current.now)).toBeLessThanOrEqual(1_000);
  });
});

describe("heartbeatServerNowIso: derives the server's clock from a heartbeat's own ts + age_s (T3.16)", () => {
  it("adds age_s seconds to ts to reconstruct the instant the API's scan read as 'now'", () => {
    const ts = "2026-09-08T03:50:00.000Z";
    const iso = heartbeatServerNowIso(ts, 7.5);
    expect(iso).toBe("2026-09-08T03:50:07.500Z");
  });

  it("returns null for an unparseable ts", () => {
    expect(heartbeatServerNowIso("not-a-date", 5)).toBeNull();
  });
});
