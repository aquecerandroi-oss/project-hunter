import { beforeEach, describe, expect, it, vi } from "vitest";

// `server-only` throws when imported outside Next's real "react-server"
// build condition, which Vitest never sets -- `lib/api/markets.ts` and
// `lib/server/auth.ts` both carry that guard (see tests/invitations-actions.test.ts).
vi.mock("server-only", () => ({}));

const { listMarketsMock, getServerSessionMock } = vi.hoisted(() => ({
  listMarketsMock: vi.fn(),
  getServerSessionMock: vi.fn(),
}));

vi.mock("@/lib/api/markets", () => ({ listMarkets: listMarketsMock }));
vi.mock("@/lib/server/auth", () => ({ getServerSession: getServerSessionMock }));

import { searchMarketsAction } from "@/lib/api/markets-actions";
import { MARKET_SEARCH_MAX_LENGTH } from "@/lib/api/markets-search";

beforeEach(() => {
  listMarketsMock.mockReset();
  getServerSessionMock.mockReset();
});

describe("searchMarketsAction: fails closed with no session, never issues the outbound API request (M7, security)", () => {
  it("returns an honest 'unauthenticated' outcome without calling listMarkets when there is no server session", async () => {
    getServerSessionMock.mockResolvedValue(null);

    const outcome = await searchMarketsAction("BTC");

    expect(outcome).toEqual({ ok: false, results: [], reason: "unauthenticated" });
    expect(listMarketsMock).not.toHaveBeenCalled();
  });

  it("calls listMarkets once a real session is present", async () => {
    getServerSessionMock.mockResolvedValue({ userId: "u1", token: "t1" });
    listMarketsMock.mockResolvedValue({ items: [{ exchange: "binance", symbol: "BTCUSDT" }], next_cursor: null });

    const outcome = await searchMarketsAction("BTC");

    expect(outcome).toEqual({ ok: true, results: [{ exchange: "binance", symbol: "BTCUSDT" }] });
    expect(listMarketsMock).toHaveBeenCalledWith({ q: "BTC", monitored: true, limit: 8 });
  });
});

describe("searchMarketsAction: bounds the query to the API's documented max_length (M8, security)", () => {
  it("rejects a query longer than MARKET_SEARCH_MAX_LENGTH without calling getServerSession or listMarkets", async () => {
    const tooLong = "a".repeat(MARKET_SEARCH_MAX_LENGTH + 1);

    const outcome = await searchMarketsAction(tooLong);

    expect(outcome.ok).toBe(false);
    expect(outcome.reason).toBeTruthy();
    expect(getServerSessionMock).not.toHaveBeenCalled();
    expect(listMarketsMock).not.toHaveBeenCalled();
  });

  it("accepts a query exactly at the max length", async () => {
    getServerSessionMock.mockResolvedValue({ userId: "u1", token: "t1" });
    listMarketsMock.mockResolvedValue({ items: [], next_cursor: null });
    const atLimit = "a".repeat(MARKET_SEARCH_MAX_LENGTH);

    const outcome = await searchMarketsAction(atLimit);

    expect(outcome.ok).toBe(true);
    expect(listMarketsMock).toHaveBeenCalled();
  });
});

describe("searchMarketsAction: an empty query is a real, cheap idle state (no session/API call needed)", () => {
  it("returns an empty ok result for a blank/whitespace-only query without calling getServerSession", async () => {
    const outcome = await searchMarketsAction("   ");

    expect(outcome).toEqual({ ok: true, results: [] });
    expect(getServerSessionMock).not.toHaveBeenCalled();
  });
});
