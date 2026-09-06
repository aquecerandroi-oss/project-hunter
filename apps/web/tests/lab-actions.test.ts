import { beforeEach, describe, expect, it, vi } from "vitest";

// `server-only` throws when imported outside Next's real "react-server"
// build condition, which Vitest never sets (see tests/invitations-actions.test.ts).
vi.mock("server-only", () => ({}));

const { listMarketsMock, getServerSessionMock } = vi.hoisted(() => ({
  listMarketsMock: vi.fn(),
  getServerSessionMock: vi.fn(),
}));

vi.mock("@/lib/api/markets", () => ({ listMarkets: listMarketsMock }));
vi.mock("@/lib/api/lab", () => ({ getLabSignals: vi.fn() }));
vi.mock("@/lib/server/auth", () => ({ getServerSession: getServerSessionMock }));

import { resolveMarketHrefAction } from "@/lib/api/lab-actions";

beforeEach(() => {
  listMarketsMock.mockReset();
  getServerSessionMock.mockReset().mockResolvedValue({ userId: "u1", token: "t1" });
});

describe("resolveMarketHrefAction: exactly one match navigates straight to the market detail page", () => {
  it("returns the real /markets/[exchange]/[symbol] link when listMarkets resolves to a single exact match", async () => {
    listMarketsMock.mockResolvedValue({ items: [{ exchange: "binance", symbol: "AAAAUSDT" }], next_cursor: null });

    const href = await resolveMarketHrefAction("acme", "AAAAUSDT");

    expect(href).toBe("/acme/markets/binance/AAAAUSDT");
    expect(listMarketsMock).toHaveBeenCalledWith({ q: "AAAAUSDT", limit: 10 });
  });
});

describe("resolveMarketHrefAction: zero matches falls back to the honest search page", () => {
  it("returns the /markets?q= search fallback when listMarkets resolves to no items", async () => {
    listMarketsMock.mockResolvedValue({ items: [], next_cursor: null });

    const href = await resolveMarketHrefAction("acme", "AAAAUSDT");

    expect(href).toBe("/acme/markets?q=AAAAUSDT");
  });
});

describe("resolveMarketHrefAction: several matches (same symbol, more than one exchange) never guesses", () => {
  it("returns the search fallback instead of picking one exchange arbitrarily", async () => {
    listMarketsMock.mockResolvedValue({
      items: [
        { exchange: "binance", symbol: "AAAAUSDT" },
        { exchange: "bybit", symbol: "AAAAUSDT" },
      ],
      next_cursor: null,
    });

    const href = await resolveMarketHrefAction("acme", "AAAAUSDT");

    expect(href).toBe("/acme/markets?q=AAAAUSDT");
  });
});

describe("resolveMarketHrefAction: fails closed with no session, never calls listMarkets", () => {
  it("returns the search fallback without hitting the API when there is no server session", async () => {
    getServerSessionMock.mockResolvedValue(null);

    const href = await resolveMarketHrefAction("acme", "AAAAUSDT");

    expect(href).toBe("/acme/markets?q=AAAAUSDT");
    expect(listMarketsMock).not.toHaveBeenCalled();
  });
});

describe("resolveMarketHrefAction: an unexpected API failure still falls back honestly", () => {
  it("returns the search fallback instead of throwing when listMarkets rejects", async () => {
    listMarketsMock.mockRejectedValue(new Error("network down"));

    const href = await resolveMarketHrefAction("acme", "AAAAUSDT");

    expect(href).toBe("/acme/markets?q=AAAAUSDT");
  });
});
