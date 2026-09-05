import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MarketRow } from "@/components/markets/market-row";
import type { MarketRow as MarketRowData } from "@/lib/api/types";

afterEach(cleanup);

const row: MarketRowData = {
  exchange: "binance",
  symbol: "BTCUSDT",
  base_asset: "BTC",
  quote_asset: "USDT",
  market_type: "perpetual",
  status: "active",
  is_monitored: true,
  monitor_rank: 1,
  last_price: "79956.90",
  bid: "79956.80",
  ask: "79957.00",
  spread_pct: "0.0000025",
  volume_24h: "12345.6",
  quote_volume_24h: "987654321.0",
  price_change_24h_pct: "1.25",
  mark_price: "79957.10",
  open_interest: "1000",
  funding_rate: "0.0001",
  funding_kind: "estimated",
  last_update: "2026-09-05T16:40:00Z",
  data_quality: "ok",
  has_open_gap: false,
  components: {
    ticker: { ts: "2026-09-05T16:40:00Z", age_ms: 500, quality: "ok" },
    book: { ts: "2026-09-05T16:40:00Z", age_ms: 500, quality: "ok" },
    mark: { ts: "2026-09-05T16:40:00Z", age_ms: 500, quality: "ok" },
    open_interest: null,
    funding: null,
  },
} as unknown as MarketRowData;

function renderRow(onOpen: () => void) {
  return render(
    <table>
      <tbody>
        <MarketRow id="r1" orgSlug="ever" row={row} staleAfterMs={10_000} rowHeight={40} ariaRowIndex={2} onOpen={onOpen} />
      </tbody>
    </table>,
  );
}

describe("MarketRow click-to-open (owner report 2026-09-05: 'cliquei na linha, não abriu')", () => {
  it("opens the detail when any cell of the row is clicked, not only the symbol link", () => {
    const onOpen = vi.fn();
    renderRow(onOpen);
    fireEvent.click(screen.getByText("79956.90"));
    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it("lets the symbol link handle its own click (no double navigation)", () => {
    const onOpen = vi.fn();
    renderRow(onOpen);
    fireEvent.click(screen.getByRole("link", { name: "BTCUSDT" }));
    expect(onOpen).not.toHaveBeenCalled();
  });
});
