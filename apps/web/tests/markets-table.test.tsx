import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@clerk/nextjs", () => ({
  useAuth: () => ({ getToken: async () => null }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}));

afterEach(cleanup);

import { MarketsError } from "@/components/markets/markets-error";
import { MarketsTable } from "@/components/markets/markets-table";
import type { MarketRow, MarketsSummary } from "@/lib/api/types";

const summary: MarketsSummary = {
  markets_total: 2,
  markets_monitored: 2,
  markets_ok: 1,
  markets_stale: 1,
  markets_degraded: 0,
  markets_unavailable: 0,
};

function makeRow(overrides: Partial<MarketRow> = {}): MarketRow {
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

describe("MarketsTable: renders real rows, no invented data", () => {
  it("shows symbol, last price and the quality badge for each row", () => {
    render(<MarketsTable orgSlug="acme" items={[makeRow()]} summary={summary} staleAfterMs={10_000} />);
    expect(screen.getByText("BTCUSDT")).toBeInTheDocument();
    expect(screen.getByText("65000.12")).toBeInTheDocument();
    expect(screen.getByText("OK")).toBeInTheDocument();
  });

  it("shows the header summary chips straight from the API's summary object", () => {
    render(<MarketsTable orgSlug="acme" items={[makeRow()]} summary={summary} staleAfterMs={10_000} />);
    expect(screen.getByText("2 mercados")).toBeInTheDocument();
    expect(screen.getByText("2 monitorados")).toBeInTheDocument();
  });

  it("filters rows by the search box", () => {
    const rows = [makeRow(), makeRow({ symbol: "ETHUSDT", base_asset: "ETH" })];
    render(<MarketsTable orgSlug="acme" items={rows} summary={summary} staleAfterMs={10_000} />);
    fireEvent.change(screen.getByLabelText("Buscar mercado"), { target: { value: "ETH" } });
    expect(screen.queryByText("BTCUSDT")).not.toBeInTheDocument();
    expect(screen.getByText("ETHUSDT")).toBeInTheDocument();
  });
});

describe("MarketsTable: honest about a truncated universe (F6)", () => {
  it("says the list is truncated when the API reported more pages via next_cursor", () => {
    render(<MarketsTable orgSlug="acme" items={[makeRow()]} summary={summary} staleAfterMs={10_000} truncated />);
    expect(screen.getByText(/Mostrando os primeiros 1 mercados monitorados/)).toBeInTheDocument();
  });

  it("says nothing about truncation when the API's next_cursor was null", () => {
    render(<MarketsTable orgSlug="acme" items={[makeRow()]} summary={summary} staleAfterMs={10_000} truncated={false} />);
    expect(screen.queryByText(/Mostrando os primeiros/)).not.toBeInTheDocument();
  });
});

describe("MarketsTable: sortable headers expose aria-sort (F9)", () => {
  it("marks the actively sorted column and marks the rest as none", () => {
    const rows = [makeRow(), makeRow({ symbol: "ETHUSDT", base_asset: "ETH" })];
    render(<MarketsTable orgSlug="acme" items={rows} summary={summary} staleAfterMs={10_000} />);

    // Default sort is quote_volume_24h desc (see MarketsTable's initial state).
    expect(screen.getByRole("columnheader", { name: /24h Vol/ })).toHaveAttribute("aria-sort", "descending");
    expect(screen.getByRole("columnheader", { name: "Mercado" })).toHaveAttribute("aria-sort", "none");
    expect(screen.getByRole("columnheader", { name: "Status" })).not.toHaveAttribute("aria-sort");
  });

  it("flips to ascending on a second click of the same header", () => {
    render(<MarketsTable orgSlug="acme" items={[makeRow()]} summary={summary} staleAfterMs={10_000} />);
    const header = screen.getByRole("columnheader", { name: /24h Vol/ });
    fireEvent.click(screen.getByRole("button", { name: /24h Vol/ }));
    expect(header).toHaveAttribute("aria-sort", "ascending");
  });
});

describe("MarketsTable: honest empty universe", () => {
  it("says the market-worker needs to be running instead of an empty table", () => {
    render(<MarketsTable orgSlug="acme" items={[]} summary={summary} staleAfterMs={10_000} />);
    expect(screen.getByText(/Nenhum mercado monitorado ainda/)).toBeInTheDocument();
  });
});

describe("MarketsError: honest failure state", () => {
  it("shows the real reason, never a stale-looking table", () => {
    render(<MarketsError reason="timeout" />);
    expect(screen.getByText(/Mercados indisponíveis: timeout/)).toBeInTheDocument();
  });
});

describe("MarketsTable: a null base_asset must not crash the search filter (H1)", () => {
  it("renders and lets the user type into the search box when a row's base_asset is null", () => {
    const rows = [makeRow({ base_asset: null }), makeRow({ symbol: "ETHUSDT", base_asset: "ETH" })];
    render(<MarketsTable orgSlug="acme" items={rows} summary={summary} staleAfterMs={10_000} />);

    // The old hand-written `MarketRow` typed `base_asset` as a non-nullable
    // `string`; `row.base_asset.toLowerCase()` on a `null` row threw
    // `Cannot read properties of null` the moment a character was typed here.
    // Typing anything at all without throwing is the point of this test.
    fireEvent.change(screen.getByLabelText("Buscar mercado"), { target: { value: "b" } });

    expect(screen.getByText("BTCUSDT")).toBeInTheDocument();
    expect(screen.queryByText("ETHUSDT")).not.toBeInTheDocument();
  });

  it("a null base_asset simply never matches a search term (no crash, no false match)", () => {
    const rows = [makeRow({ base_asset: null }), makeRow({ symbol: "ETHUSDT", base_asset: "ETH" })];
    render(<MarketsTable orgSlug="acme" items={rows} summary={summary} staleAfterMs={10_000} />);

    fireEvent.change(screen.getByLabelText("Buscar mercado"), { target: { value: "ETH" } });

    expect(screen.queryByText("BTCUSDT")).not.toBeInTheDocument();
    expect(screen.getByText("ETHUSDT")).toBeInTheDocument();
  });
});

describe("MarketsTable: QualityBadge ages off the API's own stale_after_ms, not a hardcoded client constant (H2)", () => {
  it("reads a 7s-old component as stale when the API's stale_after_ms is 5000", () => {
    const staleTs = new Date(Date.now() - 7_000).toISOString();
    const row = makeRow({
      components: {
        ticker: { ts: staleTs, age_ms: 7_000, quality: "ok" },
        book: { ts: staleTs, age_ms: 7_000, quality: "ok" },
        mark: { ts: staleTs, age_ms: 7_000, quality: "ok" },
        open_interest: { ts: staleTs, age_ms: 7_000 },
        funding: { ts: staleTs, age_ms: 7_000, kind: "realized" },
      },
    });

    render(<MarketsTable orgSlug="acme" items={[row]} summary={summary} staleAfterMs={5_000} />);

    // A client hardcoded to the old 10s default would still show "OK" here.
    expect(screen.queryByText("OK")).not.toBeInTheDocument();
    expect(screen.getByText(/^atrasado/)).toBeInTheDocument();
  });
});
