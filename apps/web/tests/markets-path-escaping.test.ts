import { beforeEach, describe, expect, it, vi } from "vitest";

// `server-only` throws outside Next's "react-server" condition, which Vitest
// never sets -- same guard the other lib/api tests mock away.
vi.mock("server-only", () => ({}));

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }));
vi.mock("@/lib/server/api", () => ({ apiFetch: apiFetchMock }));

import { getCandles, getMarket } from "@/lib/api/markets";

beforeEach(() => {
  apiFetchMock.mockReset();
  apiFetchMock.mockResolvedValue({});
});

// HIGH (security review of the T1.6b proof, 2026-09-05): `exchange` and
// `symbol` are Next.js dynamic route segments -- URL-decoded by the router,
// so fully caller-controlled. Unescaped, WHATWG URL parsing resolves `..`
// BEFORE the request leaves the server, and `apiFetch` targets API_URL, the
// internal service address the browser is deliberately not meant to reach,
// with the caller's own bearer token.
describe("market path segments are escaped before they reach the internal API", () => {
  it("cannot climb out of /api/v1/markets with ../ in the symbol", async () => {
    await getMarket("binance", "BTCUSDT/../../../metrics");

    const path = apiFetchMock.mock.calls[0]![0] as string;
    expect(path).toBe("/api/v1/markets/binance/BTCUSDT%2F..%2F..%2F..%2Fmetrics");
    expect(new URL(path, "http://api.internal:8000").pathname).toContain("/api/v1/markets/");
  });

  it("cannot inject a query string or a fragment through the exchange", async () => {
    await getMarket("binance?x=1#frag", "BTCUSDT");

    expect(apiFetchMock.mock.calls[0]![0]).toBe(
      "/api/v1/markets/binance%3Fx%3D1%23frag/BTCUSDT",
    );
  });

  it("escapes the same way on the candles route, keeping its own query string", async () => {
    await getCandles("binance", "BTCUSDT/../..", { limit: 10 });

    // `/candles` is a literal segment the caller appends, so it stays a real
    // separator; what matters is that the caller-controlled part is one opaque
    // segment (`BTCUSDT%2F..%2F..`), which URL normalization does not treat as
    // `..` and therefore cannot climb out of `/api/v1/markets/`.
    const path = apiFetchMock.mock.calls[0]![0] as string;
    expect(path).toBe("/api/v1/markets/binance/BTCUSDT%2F..%2F../candles?limit=10");
    expect(new URL(path, "http://api.internal:8000").pathname).toBe(
      "/api/v1/markets/binance/BTCUSDT%2F..%2F../candles",
    );
  });

  it("round-trips the real Chinese symbols Binance lists (rank 19 and 42 by 24h volume on 2026-09-05)", async () => {
    await getMarket("binance", "牛来USDT");

    const path = apiFetchMock.mock.calls[0]![0] as string;
    expect(path).toBe("/api/v1/markets/binance/%E7%89%9B%E6%9D%A5USDT");
    expect(decodeURIComponent(new URL(path, "http://x").pathname.split("/")[5]!)).toBe("牛来USDT");
  });
});
