import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

afterEach(cleanup);

import { OrderBook } from "@/components/markets/order-book";
import type { MarketBook } from "@/lib/api/types";

const book: MarketBook = {
  ts: new Date().toISOString(),
  depth: 20,
  kind: "snapshot",
  bids: [{ price: "64999.00", qty: "0.5" }],
  asks: [{ price: "65001.00", qty: "0.4" }],
};

describe("OrderBook: a failed hot-state read is not the same fact as 'no book' (H3)", () => {
  it("shows a distinct outage message when hot_state_ok is false, not the legitimate-empty message", () => {
    render(<OrderBook book={null} hotStateOk={false} />);
    expect(screen.getByText(/Book indisponível: falha ao ler/)).toBeInTheDocument();
  });

  it("shows the plain 'no book' message when the read succeeded but there is genuinely no book", () => {
    render(<OrderBook book={null} hotStateOk />);
    expect(screen.getByText("Book indisponível.")).toBeInTheDocument();
    expect(screen.queryByText(/falha ao ler/)).not.toBeInTheDocument();
  });

  it("renders bids and asks when the read succeeded and a book is present", () => {
    render(<OrderBook book={book} hotStateOk />);
    expect(screen.getByText("64999.00")).toBeInTheDocument();
    expect(screen.getByText("65001.00")).toBeInTheDocument();
  });
});
