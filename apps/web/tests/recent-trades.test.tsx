import { cleanup, render, screen, waitFor } from "@testing-library/react";
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

describe("RecentTrades: timestamp renders UTC immediately, local offset only as a client-only enhancement (H2, T1.5b fix pass)", () => {
  it("shows the UTC clock on the very first render, matching the ISO timestamp's own UTC components", () => {
    render(<RecentTrades trades={[makeTrade({ ts: "2026-09-05T14:32:10.000Z" })]} hotStateOk />);
    // A naive split (UTC in one span, local time computed synchronously in
    // the same render) is exactly the bug: the server and the browser can
    // disagree on "local", but never on this UTC part -- it must be present
    // immediately, not only after some client-only effect runs.
    expect(screen.getByText(/14:32:10 UTC/)).toBeInTheDocument();
  });

  it("adds the local offset in parentheses once mounted, without ever losing the UTC part", async () => {
    render(<RecentTrades trades={[makeTrade({ ts: "2026-09-05T14:32:10.000Z" })]} hotStateOk />);
    await waitFor(() => expect(screen.getByText(/14:32:10 UTC \(\d{2}:\d{2}:\d{2} [+-]\d{2}:\d{2}\)/)).toBeInTheDocument());
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
