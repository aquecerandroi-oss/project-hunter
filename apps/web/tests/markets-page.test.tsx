import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// `server-only` throws when imported outside Next's real "react-server"
// build condition, which Vitest never sets (see tests/invitations-actions.test.ts).
vi.mock("server-only", () => ({}));

const { resolveOrgContextMock, listMarketsMock } = vi.hoisted(() => ({
  resolveOrgContextMock: vi.fn(),
  listMarketsMock: vi.fn(),
}));

vi.mock("@/lib/api/org-context", () => ({ resolveOrgContext: resolveOrgContextMock }));
vi.mock("@/lib/api/markets", () => ({ listMarkets: listMarketsMock }));
vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("notFound() should not be called in these tests");
  },
  useRouter: () => ({ refresh: vi.fn() }),
}));
vi.mock("@clerk/nextjs", () => ({
  useAuth: () => ({ getToken: async () => null }),
}));
vi.mock("@/hooks/useMarketChannels", () => ({ useMarketChannels: () => ({ status: "closed", messages: {} }) }));

import MarketsPage from "@/app/(app)/[orgSlug]/markets/page";
import type { MarketRow, MarketsListResponse, MembershipOut } from "@/lib/api/types";

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

const summary: MarketsListResponse["summary"] = {
  markets_total: 1,
  markets_monitored: 1,
  markets_ok: 1,
  markets_stale: 0,
  markets_degraded: 0,
  markets_unavailable: 0,
};

function makeRow(): MarketRow {
  const now = new Date().toISOString();
  return {
    id: "11111111-1111-1111-1111-111111111111",
    exchange: "binance",
    symbol: "BTCUSDT",
    base_asset: "BTC",
    quote_asset: "USDT",
    market_type: "perpetual",
    status: "active",
    is_monitored: true,
    monitor_rank: 1,
    last_price: "65000.12",
    bid: "65000.00",
    ask: "65000.24",
    spread_pct: "0.01",
    volume_24h: "1000",
    quote_volume_24h: "65000000",
    price_change_24h_pct: "1.23",
    mark_price: "65000.12",
    open_interest: "500",
    funding_rate: "0.0001",
    funding_kind: "realized",
    last_update: now,
    data_quality: "ok",
    has_open_gap: false,
    components: {
      ticker: { ts: now, age_ms: 0, quality: "ok" },
      book: { ts: now, age_ms: 0, quality: "ok" },
      mark: { ts: now, age_ms: 0, quality: "ok" },
      open_interest: { ts: now, age_ms: 0 },
      funding: { ts: now, age_ms: 0, kind: "realized" },
    },
  };
}

beforeEach(() => {
  resolveOrgContextMock.mockReset().mockResolvedValue(membership);
  listMarketsMock.mockReset();
});

afterEach(cleanup);

describe("MarketsPage: truncation wiring flows from the real API response, not the component's own prop default (H10)", () => {
  it("says the list is truncated when the page's own listMarkets() call reports a non-null next_cursor", async () => {
    listMarketsMock.mockResolvedValue({
      items: [makeRow()],
      next_cursor: "cursor-2",
      summary,
      stale_after_ms: 10_000,
    });

    const jsx = await MarketsPage({ params: Promise.resolve({ orgSlug: "acme" }) });
    render(jsx);

    expect(screen.getByText(/Mostrando os primeiros 1 mercados monitorados/)).toBeInTheDocument();
  });

  it("says nothing about truncation when the page's own listMarkets() call reports next_cursor: null", async () => {
    listMarketsMock.mockResolvedValue({
      items: [makeRow()],
      next_cursor: null,
      summary,
      stale_after_ms: 10_000,
    });

    const jsx = await MarketsPage({ params: Promise.resolve({ orgSlug: "acme" }) });
    render(jsx);

    expect(screen.queryByText(/Mostrando os primeiros/)).not.toBeInTheDocument();
  });
});
