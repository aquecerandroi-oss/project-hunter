import { renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

import { useMarketChannels } from "@/hooks/useMarketChannels";

function manyChannels(count: number, offset = 0): string[] {
  return Array.from({ length: count }, (_, i) => `rt:market:binance:SYM${i + offset}`);
}

beforeEach(() => {
  // No `NEXT_PUBLIC_WS_URL` -- the connection effect bails out immediately
  // (`hooks/useMarketChannels.ts`'s own guard), so this exercises only the
  // cap-warning logic under test, never a real `RealtimeClient`.
  vi.stubEnv("NEXT_PUBLIC_WS_URL", "");
  vi.spyOn(console, "warn").mockImplementation(() => undefined);
});

function capWarnCalls(): unknown[][] {
  return vi.mocked(console.warn).mock.calls.filter(([line]) => typeof line === "string" && line.includes("market_channels_capped"));
}

describe("useMarketChannels: the cap warning is a real effect, not a render-body side effect (F10)", () => {
  it("logs once when first rendered over the cap", () => {
    renderHook((props: { channels: string[] }) => useMarketChannels({ channels: props.channels, getAuthToken: () => null }), {
      initialProps: { channels: manyChannels(60) },
    });

    expect(capWarnCalls()).toHaveLength(1);
  });

  it("does not log again on a re-render that stays over the cap with the same channel count", () => {
    const { rerender } = renderHook(
      (props: { channels: string[] }) => useMarketChannels({ channels: props.channels, getAuthToken: () => null }),
      { initialProps: { channels: manyChannels(60) } },
    );
    expect(capWarnCalls()).toHaveLength(1);

    // Different channel names, same length/overflow condition -- a render-body
    // call would fire again here; the effect (keyed on the overflow boolean)
    // must not.
    rerender({ channels: manyChannels(60, 1) });
    expect(capWarnCalls()).toHaveLength(1);
  });

  it("never logs when under the cap", () => {
    renderHook((props: { channels: string[] }) => useMarketChannels({ channels: props.channels, getAuthToken: () => null }), {
      initialProps: { channels: manyChannels(10) },
    });

    expect(capWarnCalls()).toHaveLength(0);
  });
});
