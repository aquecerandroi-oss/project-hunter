import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@clerk/nextjs", () => ({
  useAuth: () => ({ getToken: async () => null }),
}));

const { useMarketChannelsMock } = vi.hoisted(() => ({ useMarketChannelsMock: vi.fn() }));
vi.mock("@/hooks/useMarketChannels", () => ({ useMarketChannels: useMarketChannelsMock }));

// This component never touches `lightweight-charts` directly for its own
// price/bid/ask math -- `CandlesChart` is mocked out the same way
// `candles-chart.test.tsx` mocks the library, so this file only exercises
// `MarketDetailView`'s own tick-freshness guard.
vi.mock("@/components/markets/candles-chart", () => ({ CandlesChart: () => null }));

afterEach(cleanup);

import { MarketDetailView } from "@/components/markets/market-detail-view";
import type { MarketDetail, RtMarketMessage } from "@/lib/api/types";

const now = new Date();
const lastUpdate = now.toISOString();

const detail: MarketDetail = {
  id: "11111111-1111-1111-1111-111111111111",
  exchange: "binance",
  symbol: "BTCUSDT",
  base_asset: "BTC",
  quote_asset: "USDT",
  market_type: "perpetual",
  status: "active",
  is_monitored: true,
  monitor_rank: 1,
  last_price: "65000.00",
  bid: "64999.00",
  ask: "65001.00",
  spread_pct: "0.01",
  volume_24h: "1000",
  quote_volume_24h: "65000000",
  price_change_24h_pct: "1.23",
  mark_price: "64000.00",
  open_interest: "500",
  funding_rate: "0.0001",
  funding_kind: "realized",
  last_update: lastUpdate,
  data_quality: "ok",
  has_open_gap: false,
  hot_state_ok: true,
  stale_after_ms: 10_000,
  components: {
    ticker: { ts: lastUpdate, age_ms: 0, quality: "ok" },
    book: { ts: lastUpdate, age_ms: 0, quality: "ok" },
    mark: { ts: lastUpdate, age_ms: 0, quality: "ok" },
    open_interest: { ts: lastUpdate, age_ms: 0 },
    funding: { ts: lastUpdate, age_ms: 0, kind: "realized" },
  },
  book: null,
  recent_trades: [],
};

/** `priceTs`/`bookTs` default to `ts` unless overridden -- most tests only care about one axis at a time. */
function tickAt(ts: string, price: string, overrides: Partial<RtMarketMessage> = {}): RtMarketMessage {
  return {
    exchange: "binance",
    symbol: "BTCUSDT",
    price,
    bid: null,
    ask: null,
    volume_delta: null,
    trades_count: null,
    book_imbalance_5: null,
    ts,
    price_ts: ts,
    book_ts: ts,
    ...overrides,
  };
}

function mockTick(tick: RtMarketMessage): void {
  useMarketChannelsMock.mockReturnValue({
    status: "open",
    messages: { "rt:market:binance:BTCUSDT": tick },
  });
}

beforeEach(() => {
  useMarketChannelsMock.mockReset();
});

describe("MarketDetailView: a stale tick must not shadow a fresher server-fetched price (T1.5 review F2 follow-up)", () => {
  it("keeps the server-fetched price when the realtime tick's price_ts is older than the ticker component's own ts", () => {
    const staleTick = tickAt(new Date(now.getTime() - 60_000).toISOString(), "1.00");
    mockTick(staleTick);

    render(<MarketDetailView detail={detail} candles={[]} />);

    expect(screen.getByText("65000.00")).toBeInTheDocument();
    expect(screen.queryByText("1.00")).not.toBeInTheDocument();
  });

  it("adopts the realtime tick's price when price_ts is fresher than the ticker component's own ts", () => {
    const freshTick = tickAt(new Date(now.getTime() + 60_000).toISOString(), "65500.00");
    mockTick(freshTick);

    render(<MarketDetailView detail={detail} candles={[]} />);

    expect(screen.getByText("65500.00")).toBeInTheDocument();
    expect(screen.queryByText("65000.00")).not.toBeInTheDocument();
  });
});

describe("MarketDetailView: the price and the book age off their OWN timestamps, not the coalesced aggregate (H4)", () => {
  it("does not adopt a fresh-looking price from a tick whose price_ts is missing, even though ts is fresh", () => {
    const bookOnlyTick = tickAt(new Date(now.getTime() + 60_000).toISOString(), "99999.00", { price_ts: null });
    mockTick(bookOnlyTick);

    render(<MarketDetailView detail={detail} candles={[]} />);

    // The tick's aggregate `ts` is fresh, but `price_ts` is missing -- the
    // old, honest price must still be shown, not the tick's price.
    expect(screen.getByText("65000.00")).toBeInTheDocument();
    expect(screen.queryByText("99999.00")).not.toBeInTheDocument();
  });

  it("a book-only tick (fresh book_ts, stale price_ts) does not shadow the server price", () => {
    const bookOnlyTick = tickAt(new Date(now.getTime() - 60_000).toISOString(), "1.00", {
      book_ts: new Date(now.getTime() + 60_000).toISOString(),
    });
    mockTick(bookOnlyTick);

    render(<MarketDetailView detail={detail} candles={[]} />);

    expect(screen.getByText("65000.00")).toBeInTheDocument();
    expect(screen.queryByText("1.00")).not.toBeInTheDocument();
  });
});

describe("MarketDetailView: honest states for a failed hot-state read (H3)", () => {
  it("shows outage messages for both book and trades when hot_state_ok is false, never 'nothing here'", () => {
    useMarketChannelsMock.mockReturnValue({ status: "closed", messages: {} });
    const failedDetail: MarketDetail = { ...detail, hot_state_ok: false, book: null, recent_trades: null };

    render(<MarketDetailView detail={failedDetail} candles={[]} />);

    expect(screen.getByText(/Book indisponível: falha ao ler/)).toBeInTheDocument();
    expect(screen.getByText(/Trades indisponíveis: falha ao ler/)).toBeInTheDocument();
  });
});

describe("MarketDetailView: candles isolated from the rest of the page (H5)", () => {
  it("shows an honest candles-unavailable message without hiding price/book/trades", () => {
    useMarketChannelsMock.mockReturnValue({ status: "closed", messages: {} });

    render(<MarketDetailView detail={detail} candles={[]} candlesError="timeout" />);

    expect(screen.getByText(/Candles indisponíveis: timeout/)).toBeInTheDocument();
    expect(screen.getByText("65000.00")).toBeInTheDocument();
  });
});
