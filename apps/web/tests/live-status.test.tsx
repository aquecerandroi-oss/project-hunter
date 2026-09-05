import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@clerk/nextjs", () => ({
  useAuth: () => ({ getToken: async () => null }),
}));

const { useMarketChannelsMock } = vi.hoisted(() => ({ useMarketChannelsMock: vi.fn() }));
vi.mock("@/hooks/useMarketChannels", () => ({ useMarketChannels: useMarketChannelsMock }));

afterEach(cleanup);

import { LiveStatus } from "@/components/system/live-status";
import type { MarketStatusResponse, RtSystemMessage } from "@/lib/api/types";

type UseMarketChannelsOptions = { onMessage?: (channel: string, payload: unknown) => void };

beforeEach(() => {
  useMarketChannelsMock.mockReset().mockImplementation(() => ({
    status: "open" as const,
    messages: {},
  }));
});

const withData: MarketStatusResponse = {
  exchanges: [
    {
      exchange: "binance",
      ws_state: "connected",
      last_event_at: new Date().toISOString(),
      last_event_age_ms: 220,
      markets_monitored: 200,
      open_gaps: 0,
      reconnects: 0,
    },
  ],
  markets_monitored_total: 200,
  updated_at: new Date().toISOString(),
};

const noHeartbeat: MarketStatusResponse = { exchanges: [], markets_monitored_total: 0, updated_at: new Date().toISOString() };

describe("LiveStatus (full): real per-exchange WS state", () => {
  it("shows the exchange, its WS state and the total monitored count", () => {
    render(<LiveStatus variant="full" initial={withData} />);
    expect(screen.getByText("binance")).toBeInTheDocument();
    expect(screen.getByText("CONNECTED")).toBeInTheDocument();
    expect(screen.getByText("200")).toBeInTheDocument();
  });

  it("says 'sem heartbeat' when the endpoint answered but no exchange ever reported", () => {
    render(<LiveStatus variant="full" initial={noHeartbeat} />);
    expect(screen.getByText("Market worker: sem heartbeat")).toBeInTheDocument();
  });
});

describe("LiveStatus (full): the header total never contradicts the rows (F7)", () => {
  it("derives the total from the live exchange rows, not the frozen initial snapshot", () => {
    let capturedOnMessage: ((channel: string, payload: unknown) => void) | undefined;
    useMarketChannelsMock.mockImplementation((opts: UseMarketChannelsOptions) => {
      capturedOnMessage = opts.onMessage;
      return { status: "open" as const, messages: {} };
    });

    render(<LiveStatus variant="full" initial={withData} />);
    expect(screen.getByText("200")).toBeInTheDocument();

    const patch: RtSystemMessage = {
      type: "market_status",
      exchange: "binance",
      ws_state: "connected",
      last_event_at: new Date().toISOString(),
      markets_monitored: 150,
      open_gaps: 0,
      ts: new Date().toISOString(),
    };
    act(() => {
      capturedOnMessage?.("rt:system", patch);
    });

    expect(screen.getByText("150")).toBeInTheDocument();
    expect(screen.queryByText("200")).not.toBeInTheDocument();
  });

  it("sums multiple exchanges' live rows for the header total", () => {
    let capturedOnMessage: ((channel: string, payload: unknown) => void) | undefined;
    useMarketChannelsMock.mockImplementation((opts: UseMarketChannelsOptions) => {
      capturedOnMessage = opts.onMessage;
      return { status: "open" as const, messages: {} };
    });

    const twoExchanges: MarketStatusResponse = {
      exchanges: [
        { exchange: "binance", ws_state: "connected", last_event_at: new Date().toISOString(), last_event_age_ms: 100, markets_monitored: 200, open_gaps: 0, reconnects: 0 },
      ],
      markets_monitored_total: 200,
      updated_at: new Date().toISOString(),
    };
    render(<LiveStatus variant="full" initial={twoExchanges} />);

    const bybitJoin: RtSystemMessage = {
      type: "market_status",
      exchange: "bybit",
      ws_state: "connected",
      last_event_at: new Date().toISOString(),
      markets_monitored: 50,
      open_gaps: 0,
      ts: new Date().toISOString(),
    };
    act(() => {
      capturedOnMessage?.("rt:system", bybitJoin);
    });

    expect(screen.getByText("250")).toBeInTheDocument();
  });
});

describe("LiveStatus (compact): topbar summary", () => {
  it("summarizes a single exchange as 'name · WS_STATE · N mercados · age'", () => {
    render(<LiveStatus variant="compact" initial={withData} />);
    expect(screen.getByText(/binance · CONNECTED · 200 mercados/)).toBeInTheDocument();
  });

  it("is honest about no heartbeat too, not just a silent dot", () => {
    render(<LiveStatus variant="compact" initial={noHeartbeat} />);
    expect(screen.getByText("Market worker: sem heartbeat")).toBeInTheDocument();
  });
});

describe("LiveStatus (compact): the exchange's own ws_state is in the visible text, not colour-only (H8)", () => {
  it("names the worst exchange's ws_state in the label for a mixed set", () => {
    const mixed: MarketStatusResponse = {
      exchanges: [
        { exchange: "binance", ws_state: "connected", last_event_at: new Date().toISOString(), last_event_age_ms: 100, markets_monitored: 200, open_gaps: 0, reconnects: 0 },
        { exchange: "bybit", ws_state: "reconnecting", last_event_at: new Date().toISOString(), last_event_age_ms: 100, markets_monitored: 50, open_gaps: 0, reconnects: 2 },
      ],
      markets_monitored_total: 250,
      updated_at: new Date().toISOString(),
    };
    render(<LiveStatus variant="compact" initial={mixed} />);
    expect(screen.getByText(/2 exchanges · RECONNECTING · 250 mercados/)).toBeInTheDocument();
  });
});

describe("LiveStatus (compact): the worst-state reducer respects down > reconnecting > connected (H8)", () => {
  it("does not render green for a connected + reconnecting mix", () => {
    const mixed: MarketStatusResponse = {
      exchanges: [
        { exchange: "binance", ws_state: "connected", last_event_at: new Date().toISOString(), last_event_age_ms: 100, markets_monitored: 200, open_gaps: 0, reconnects: 0 },
        { exchange: "bybit", ws_state: "reconnecting", last_event_at: new Date().toISOString(), last_event_age_ms: 100, markets_monitored: 50, open_gaps: 0, reconnects: 2 },
      ],
      markets_monitored_total: 250,
      updated_at: new Date().toISOString(),
    };
    const { container } = render(<LiveStatus variant="compact" initial={mixed} />);
    const dot = container.querySelector("span.rounded-full");
    expect(dot).not.toBeNull();
    expect(dot?.className).toContain("bg-warning");
    expect(dot?.className).not.toContain("bg-green");
  });
});

describe("LiveStatus: reconciles a fresh server snapshot, not just the value read at mount (H6)", () => {
  it("shows a worker dropping from 200 to 150 monitored markets once a newer initial prop arrives", () => {
    const { rerender } = render(<LiveStatus variant="full" initial={withData} />);
    expect(screen.getByText("200")).toBeInTheDocument();

    const droppedLater: MarketStatusResponse = {
      exchanges: [
        {
          exchange: "binance",
          ws_state: "connected",
          last_event_at: new Date().toISOString(),
          last_event_age_ms: 220,
          markets_monitored: 150,
          open_gaps: 0,
          reconnects: 0,
        },
      ],
      markets_monitored_total: 150,
      updated_at: new Date(Date.now() + 60_000).toISOString(),
    };
    // Simulates `AutoRefresh`'s `router.refresh()` producing a fresh
    // server-fetched `initial` prop on the next render of this same
    // component instance -- a plain `useState(initial)` ignores this.
    rerender(<LiveStatus variant="full" initial={droppedLater} />);

    expect(screen.getByText("150")).toBeInTheDocument();
    expect(screen.queryByText("200")).not.toBeInTheDocument();
  });

  it("an older initial snapshot must not undo a newer realtime patch already applied", () => {
    let capturedOnMessage: ((channel: string, payload: unknown) => void) | undefined;
    useMarketChannelsMock.mockImplementation((opts: UseMarketChannelsOptions) => {
      capturedOnMessage = opts.onMessage;
      return { status: "open" as const, messages: {} };
    });

    const { rerender } = render(<LiveStatus variant="full" initial={withData} />);

    const freshPatch: RtSystemMessage = {
      type: "market_status",
      exchange: "binance",
      ws_state: "connected",
      last_event_at: new Date().toISOString(),
      markets_monitored: 175,
      open_gaps: 0,
      ts: new Date(Date.now() + 120_000).toISOString(),
    };
    act(() => {
      capturedOnMessage?.("rt:system", freshPatch);
    });
    expect(screen.getByText("175")).toBeInTheDocument();

    // Re-render with the SAME (now stale, relative to the patch just
    // applied) `initial` snapshot -- as could happen if `AutoRefresh` fires
    // again before the next real change lands server-side.
    rerender(<LiveStatus variant="full" initial={{ ...withData }} />);

    expect(screen.getByText("175")).toBeInTheDocument();
    expect(screen.queryByText("200")).not.toBeInTheDocument();
  });
});
