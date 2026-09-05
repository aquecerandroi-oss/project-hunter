import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

const { resolveOrgContextMock, getMarketMock, getCandlesMock, refreshMock, useRouterMock } = vi.hoisted(() => ({
  resolveOrgContextMock: vi.fn(),
  getMarketMock: vi.fn(),
  getCandlesMock: vi.fn(),
  refreshMock: vi.fn(),
  useRouterMock: vi.fn(),
}));

vi.mock("@/lib/api/org-context", () => ({ resolveOrgContext: resolveOrgContextMock }));
vi.mock("@/lib/api/markets", () => ({ getMarket: getMarketMock, getCandles: getCandlesMock }));
vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("notFound() should not be called in these tests");
  },
  useRouter: useRouterMock,
}));
vi.mock("@clerk/nextjs", () => ({
  useAuth: () => ({ getToken: async () => null }),
}));
vi.mock("@/hooks/useMarketChannels", () => ({ useMarketChannels: () => ({ status: "closed", messages: {} }) }));
vi.mock("@/components/markets/candles-chart", () => ({ CandlesChart: () => null }));

import MarketDetailPage from "@/app/(app)/[orgSlug]/markets/[exchange]/[symbol]/page";
import { ApiError } from "@/lib/api-error";
import type { MarketDetail, MembershipOut } from "@/lib/api/types";

function apiError(status: number, detail: string): ApiError {
  return new ApiError({ type: "about:blank", title: "Error", status, detail });
}

const membership: MembershipOut = {
  onboarding: { completed: true, completed_at: "2026-01-01T00:00:00Z", workspace_id: "ws-1" },
  organization: {
    id: "org-1",
    slug: "acme",
    name: "Acme Capital",
    plan: "FREE",
    kill_switch_state: "ACTIVE",
    created_at: "2026-01-01T00:00:00Z",
  },
  role: "OWNER",
  status: "active",
};

const now = new Date().toISOString();

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
  last_update: now,
  data_quality: "ok",
  has_open_gap: false,
  hot_state_ok: true,
  stale_after_ms: 10_000,
  components: {
    ticker: { ts: now, age_ms: 0, quality: "ok" },
    book: { ts: now, age_ms: 0, quality: "ok" },
    mark: { ts: now, age_ms: 0, quality: "ok" },
    open_interest: { ts: now, age_ms: 0 },
    funding: { ts: now, age_ms: 0, kind: "realized" },
  },
  book: null,
  recent_trades: [],
};

function params() {
  return Promise.resolve({ orgSlug: "acme", exchange: "binance", symbol: "BTCUSDT" });
}

beforeEach(() => {
  resolveOrgContextMock.mockReset().mockResolvedValue(membership);
  getMarketMock.mockReset();
  getCandlesMock.mockReset();
  refreshMock.mockReset();
  useRouterMock.mockReset().mockReturnValue({ refresh: refreshMock });
});

afterEach(cleanup);

describe("MarketDetailPage: candles isolated from the rest of the detail (H5)", () => {
  it("still renders price/book/trades when only getCandles() fails", async () => {
    getMarketMock.mockResolvedValue(detail);
    getCandlesMock.mockRejectedValue(apiError(503, "candles down"));

    const jsx = await MarketDetailPage({ params: params() });
    render(jsx);

    expect(screen.getByText("65000.00")).toBeInTheDocument();
    expect(screen.getByText(/Candles indisponíveis: candles down/)).toBeInTheDocument();
  });

  it("renders everything normally when both fetches succeed", async () => {
    getMarketMock.mockResolvedValue(detail);
    getCandlesMock.mockResolvedValue([]);

    const jsx = await MarketDetailPage({ params: params() });
    render(jsx);

    expect(screen.getByText("65000.00")).toBeInTheDocument();
    expect(screen.queryByText(/Candles indisponíveis/)).not.toBeInTheDocument();
  });
});

describe("MarketDetailPage: AutoRefresh stays mounted on a failed detail fetch (H5)", () => {
  it("keeps refreshing after a transient detail failure instead of giving up for good", async () => {
    getMarketMock.mockRejectedValue(apiError(503, "detail down"));
    getCandlesMock.mockResolvedValue([]);

    const jsx = await MarketDetailPage({ params: params() });
    render(jsx);

    expect(screen.getByText(/Mercados indisponíveis: detail down/)).toBeInTheDocument();
    // `AutoRefresh` is the only component in this tree that calls
    // `useRouter()` -- it used to be mounted only in the success branch, so
    // one transient failure permanently stopped the page's automatic retry.
    // `useRouterMock` having been called at all proves `AutoRefresh` mounted
    // even though `getMarket()` rejected.
    expect(useRouterMock).toHaveBeenCalled();
  });
});
