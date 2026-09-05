import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

afterEach(cleanup);

import { RecentTrades } from "@/components/markets/recent-trades";
import type { RecentTrade } from "@/lib/api/types";

function makeTrade(overrides: Partial<RecentTrade> = {}): RecentTrade {
  return {
    ts: new Date().toISOString(),
    price: "65000.00",
    qty: "0.01",
    side: "buy",
    trade_id: "t-1",
    ...overrides,
  };
}

describe("RecentTrades: buy/sell is never colour-only (F8)", () => {
  it("gives a buy row a non-colour glyph and an aria-label naming it a purchase", () => {
    render(<RecentTrades trades={[makeTrade({ side: "buy", trade_id: "t-buy" })]} hotStateOk />);
    expect(screen.getByRole("listitem", { name: /Compra/i })).toBeInTheDocument();
    expect(screen.getByText("C")).toBeInTheDocument();
  });

  it("gives a sell row a distinct glyph and an aria-label naming it a sale", () => {
    render(<RecentTrades trades={[makeTrade({ side: "sell", trade_id: "t-sell" })]} hotStateOk />);
    expect(screen.getByRole("listitem", { name: /Venda/i })).toBeInTheDocument();
    expect(screen.getByText("V")).toBeInTheDocument();
  });

  it("still shows the honest empty state with no trades", () => {
    render(<RecentTrades trades={[]} hotStateOk />);
    expect(screen.getByText("Nenhum trade recente.")).toBeInTheDocument();
  });
});

describe("RecentTrades: a failed hot-state read is not the same fact as 'no trades' (H3)", () => {
  it("shows a distinct outage message when hot_state_ok is false, not the empty-trades message", () => {
    render(<RecentTrades trades={null} hotStateOk={false} />);
    expect(screen.getByText(/Trades indisponíveis/)).toBeInTheDocument();
    expect(screen.queryByText("Nenhum trade recente.")).not.toBeInTheDocument();
  });

  it("shows the outage message for a null trades array even if hotStateOk is somehow true (defensive)", () => {
    render(<RecentTrades trades={null} hotStateOk />);
    expect(screen.getByText(/Trades indisponíveis/)).toBeInTheDocument();
  });
});
