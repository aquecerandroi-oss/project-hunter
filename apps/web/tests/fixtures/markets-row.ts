import type { MarketRow, MarketsSummary } from "@/lib/api/types";

/**
 * Shared `MarketsTable`/`MarketRow` test fixtures (T1.5b fix pass 2): pulled
 * out of `markets-table.test.tsx` so the new M2/M3 assertions could live in
 * their own files without either duplicating this factory or pushing that
 * one file over the lint config's 350-line budget.
 */
export const summary: MarketsSummary = {
  markets_total: 2,
  markets_monitored: 2,
  markets_ok: 1,
  markets_stale: 1,
  markets_degraded: 0,
  markets_unavailable: 0,
};

export function makeRow(overrides: Partial<MarketRow> = {}): MarketRow {
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
    ...overrides,
  };
}
