import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@clerk/nextjs", () => ({
  useAuth: () => ({ getToken: async () => null }),
}));

const routerPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn(), push: routerPush }),
}));

afterEach(() => {
  cleanup();
  routerPush.mockClear();
});

import { MarketsError } from "@/components/markets/markets-error";
import { MarketsTable } from "@/components/markets/markets-table";
import { makeRow, summary } from "@/tests/fixtures/markets-row";

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

describe("MarketsTable: separate empty states (joint decision #8)", () => {
  it("says 'Nenhum resultado' for a search with no matches, distinct from the empty-universe message", () => {
    render(<MarketsTable orgSlug="acme" items={[makeRow()]} summary={summary} staleAfterMs={10_000} />);
    fireEvent.change(screen.getByLabelText("Buscar mercado"), { target: { value: "zzz-no-match" } });
    expect(screen.getByText(/Nenhum resultado para/)).toBeInTheDocument();
    expect(screen.queryByText(/Nenhum mercado monitorado ainda/)).not.toBeInTheDocument();
  });
});

describe("MarketsTable: exchange/symbol segments are URL-encoded before building a route (LOW, one-liner)", () => {
  it("encodes a symbol containing a slash in the row's own Link href", () => {
    const row = makeRow({ exchange: "binance", symbol: "WEIRD/SYM" });
    render(<MarketsTable orgSlug="acme" items={[row]} summary={summary} staleAfterMs={10_000} />);

    const link = screen.getByRole("link", { name: "WEIRD/SYM" });
    expect(link).toHaveAttribute("href", "/acme/markets/binance/WEIRD%2FSYM");
  });

  it("encodes a symbol containing a slash before router.push on Enter", () => {
    const row = makeRow({ exchange: "binance", symbol: "WEIRD/SYM" });
    render(<MarketsTable orgSlug="acme" items={[row]} summary={summary} staleAfterMs={10_000} />);
    const grid = screen.getByRole("grid", { name: "Mercados monitorados" });

    fireEvent.keyDown(grid, { key: "ArrowDown" });
    fireEvent.keyDown(grid, { key: "Enter" });

    expect(routerPush).toHaveBeenCalledWith("/acme/markets/binance/WEIRD%2FSYM");
  });
});

describe("MarketsTable: a missing 24h change is neutral, never colored as if it were positive (M4)", () => {
  it("shows the '--' placeholder in the muted color, not green, when price_change_24h_pct is null", () => {
    const row = makeRow({ price_change_24h_pct: null });
    render(<MarketsTable orgSlug="acme" items={[row]} summary={summary} staleAfterMs={10_000} />);

    const cell = screen.getByText("--").closest("td");
    expect(cell).toHaveClass("text-fg-muted");
    expect(cell).not.toHaveClass("text-green");
    expect(cell).not.toHaveClass("text-red");
  });

  it("still colors a real negative change red, and a real positive change green", () => {
    const rows = [
      makeRow({ symbol: "AUSDT", price_change_24h_pct: "-1.50" }),
      makeRow({ symbol: "BUSDT", price_change_24h_pct: "1.50" }),
    ];
    render(<MarketsTable orgSlug="acme" items={rows} summary={summary} staleAfterMs={10_000} />);

    expect(screen.getByText("-1.50%").closest("td")).toHaveClass("text-red");
    expect(screen.getByText("+1.50%").closest("td")).toHaveClass("text-green");
  });
});

// M3's off-screen-Enter guard lives in `markets-table-visibility.test.tsx`
// and M2's ARIA role tree lives in `markets-table-grid-roles.test.tsx` --
// split out to keep this file under the lint config's 350-line budget.

describe("MarketsTable: keyboard navigation (arrow keys move, Enter opens)", () => {
  it("moves the selection down/up with arrow keys and marks the active row with aria-selected", () => {
    const rows = [makeRow({ symbol: "AAAUSDT" }), makeRow({ symbol: "BBBUSDT" })];
    render(<MarketsTable orgSlug="acme" items={rows} summary={summary} staleAfterMs={10_000} />);
    const grid = screen.getByRole("grid", { name: "Mercados monitorados" });

    fireEvent.keyDown(grid, { key: "ArrowDown" });
    const firstRow = screen.getByText("AAAUSDT").closest("tr");
    expect(firstRow).toHaveAttribute("aria-selected", "true");

    fireEvent.keyDown(grid, { key: "ArrowDown" });
    const secondRow = screen.getByText("BBBUSDT").closest("tr");
    expect(secondRow).toHaveAttribute("aria-selected", "true");
    expect(firstRow).toHaveAttribute("aria-selected", "false");

    fireEvent.keyDown(grid, { key: "ArrowUp" });
    expect(firstRow).toHaveAttribute("aria-selected", "true");
  });

  it("navigates to the selected row's detail page on Enter", () => {
    const rows = [makeRow({ exchange: "binance", symbol: "AAAUSDT" })];
    render(<MarketsTable orgSlug="acme" items={rows} summary={summary} staleAfterMs={10_000} />);
    const grid = screen.getByRole("grid", { name: "Mercados monitorados" });

    fireEvent.keyDown(grid, { key: "ArrowDown" });
    fireEvent.keyDown(grid, { key: "Enter" });

    expect(routerPush).toHaveBeenCalledWith("/acme/markets/binance/AAAUSDT");
  });
});

describe("MarketsTable: a blocked Web Storage must never white-screen the whole table (NEW, Astra, T1.5b fix pass 2)", () => {
  it("still renders every row when localStorage.getItem throws SecurityError (every row calls usePriceFlash)", () => {
    const original = window.localStorage.getItem;
    window.localStorage.getItem = vi.fn(() => {
      throw new DOMException("blocked", "SecurityError");
    });

    try {
      const rows = [makeRow(), makeRow({ symbol: "ETHUSDT", base_asset: "ETH" })];
      expect(() =>
        render(<MarketsTable orgSlug="acme" items={rows} summary={summary} staleAfterMs={10_000} />),
      ).not.toThrow();
      expect(screen.getByText("BTCUSDT")).toBeInTheDocument();
      expect(screen.getByText("ETHUSDT")).toBeInTheDocument();
    } finally {
      window.localStorage.getItem = original;
    }
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
