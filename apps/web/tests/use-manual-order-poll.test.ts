import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/** Advances fake timers AND flushes the resulting promise-chain state updates inside `act()`, so `result.current` reflects them (a bare `vi.advanceTimersByTimeAsync` runs the interval + its `.then()` outside React's batching, and the hook's `setState` calls are invisible to `result.current` until something flushes them). */
async function tick(ms: number): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

const { pollManualOrderActionMock } = vi.hoisted(() => ({ pollManualOrderActionMock: vi.fn() }));
vi.mock("@/lib/api/manual-orders-actions", () => ({ pollManualOrderAction: pollManualOrderActionMock }));

import { useManualOrderPoll } from "@/hooks/useManualOrderPoll";
import type { ManualOrderOut } from "@/lib/api/manual-orders-types";

const PENDING: ManualOrderOut = {
  request_id: "req-1",
  market_id: "3f6b3b9a-6b1a-4e6a-9c1a-000000000003",
  direction: "long",
  status: "pending",
  filed_at: "2026-09-10T12:00:00Z",
  decision: null,
};

beforeEach(() => {
  pollManualOrderActionMock.mockReset();
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useManualOrderPoll: 2s cadence, <= 60s (brief item 1)", () => {
  it("returns null with no filed order and never polls", () => {
    const { result } = renderHook(() => useManualOrderPoll("org-1", "wallet-1", null));
    expect(result.current).toBeNull();
    expect(pollManualOrderActionMock).not.toHaveBeenCalled();
  });

  it("does not poll at all when the order arrives already decided", () => {
    const decided: ManualOrderOut = { ...PENDING, status: "decided" };
    const { result } = renderHook(() => useManualOrderPoll("org-1", "wallet-1", decided));
    expect(result.current).toEqual({ order: decided, settled: true, timedOut: false, error: null });
    expect(pollManualOrderActionMock).not.toHaveBeenCalled();
  });

  it("polls every 2s while pending and stops the moment the poll returns decided", async () => {
    pollManualOrderActionMock
      .mockResolvedValueOnce({ ok: true, data: { ...PENDING, decision: null } })
      .mockResolvedValueOnce({ ok: true, data: { ...PENDING, status: "decided", decision: null } });

    const { result } = renderHook(() => useManualOrderPoll("org-1", "wallet-1", PENDING));
    expect(result.current?.settled).toBe(false);

    await tick(2_000);
    expect(pollManualOrderActionMock).toHaveBeenCalledTimes(1);
    expect(result.current?.settled).toBe(false);

    await tick(2_000);
    expect(pollManualOrderActionMock).toHaveBeenCalledTimes(2);
    expect(result.current?.settled).toBe(true);

    // No further polling once settled.
    await tick(10_000);
    expect(pollManualOrderActionMock).toHaveBeenCalledTimes(2);
  });

  it("stops after 60s with timedOut=true when the engine never decides", async () => {
    pollManualOrderActionMock.mockResolvedValue({ ok: true, data: { ...PENDING, decision: null } });

    const { result } = renderHook(() => useManualOrderPoll("org-1", "wallet-1", PENDING));

    await tick(60_000);
    expect(result.current?.timedOut).toBe(true);
    expect(result.current?.settled).toBe(false);

    const callsAtTimeout = pollManualOrderActionMock.mock.calls.length;
    await tick(10_000);
    expect(pollManualOrderActionMock).toHaveBeenCalledTimes(callsAtTimeout);
  });

  it("stops and records the error on a real fetch failure, never a false 'settled'", async () => {
    pollManualOrderActionMock.mockResolvedValue({
      ok: false,
      problem: { type: "https://hunter.dev/problems/unexpected-response", title: "x", status: 502, detail: "fora do ar" },
    });

    const { result } = renderHook(() => useManualOrderPoll("org-1", "wallet-1", PENDING));

    await tick(2_000);
    expect(result.current?.error).toBe("fora do ar");
    expect(result.current?.settled).toBe(false);

    const callsAtError = pollManualOrderActionMock.mock.calls.length;
    await tick(10_000);
    expect(pollManualOrderActionMock).toHaveBeenCalledTimes(callsAtError);
  });
});
