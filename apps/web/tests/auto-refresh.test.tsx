import { act, cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { refreshMock } = vi.hoisted(() => ({ refreshMock: vi.fn() }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: refreshMock }),
}));

import { AutoRefresh } from "@/components/auto-refresh";
import { MIN_AUTO_REFRESH_INTERVAL_MS, autoRefreshIntervalMs } from "@/lib/auto-refresh-interval";

function setVisibility(state: DocumentVisibilityState): void {
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => state });
}

beforeEach(() => {
  refreshMock.mockReset();
  vi.useFakeTimers();
  setVisibility("visible");
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("AutoRefresh: keeps an already-open Server Component page from reading as stale forever (F2)", () => {
  it("calls router.refresh() on every interval tick while the tab is visible", () => {
    render(<AutoRefresh intervalMs={10_000} />);

    act(() => vi.advanceTimersByTime(10_000));
    expect(refreshMock).toHaveBeenCalledTimes(1);

    act(() => vi.advanceTimersByTime(20_000));
    expect(refreshMock).toHaveBeenCalledTimes(3);
  });

  it("does not call router.refresh() while the tab is hidden", () => {
    setVisibility("hidden");
    render(<AutoRefresh intervalMs={10_000} />);

    act(() => vi.advanceTimersByTime(30_000));
    expect(refreshMock).not.toHaveBeenCalled();
  });

  it("resumes on the next tick once the tab becomes visible again", () => {
    setVisibility("hidden");
    render(<AutoRefresh intervalMs={10_000} />);
    act(() => vi.advanceTimersByTime(10_000));
    expect(refreshMock).not.toHaveBeenCalled();

    setVisibility("visible");
    act(() => vi.advanceTimersByTime(10_000));
    expect(refreshMock).toHaveBeenCalledTimes(1);
  });

  it("clears the interval on unmount -- no refresh calls after the component is gone", () => {
    const { unmount } = render(<AutoRefresh intervalMs={10_000} />);
    unmount();

    act(() => vi.advanceTimersByTime(50_000));
    expect(refreshMock).not.toHaveBeenCalled();
  });
});

describe("autoRefreshIntervalMs: derived from the API's own stale_after_ms, never a cadence guaranteed to cross it (H9)", () => {
  it("lands comfortably below stale_after_ms instead of hardcoding a cadence independent of it", () => {
    // The old fixed 12s cadence against a 10s staleness threshold reliably
    // let book/mark cross the threshold between refreshes even under
    // perfectly healthy ingestion -- the derived interval must stay under it.
    expect(autoRefreshIntervalMs(10_000)).toBeLessThan(10_000);
  });

  it("never refreshes faster than MIN_AUTO_REFRESH_INTERVAL_MS even for a very low stale_after_ms", () => {
    expect(autoRefreshIntervalMs(1_000)).toBe(MIN_AUTO_REFRESH_INTERVAL_MS);
  });

  it("scales up for a generous stale_after_ms instead of refreshing needlessly often", () => {
    expect(autoRefreshIntervalMs(60_000)).toBe(57_000);
  });
});
