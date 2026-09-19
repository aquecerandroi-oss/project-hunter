/**
 * "Mesa spot/1" (T4.74-6): the honest empty state for an executor build that
 * predates the field, and a full render of the design §7 contract.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Spot1Panel, type Spot1 } from "@/components/meme-live/spot1-panel";

afterEach(cleanup);

function spot1(overrides: Partial<Spot1> = {}): Spot1 {
  return {
    mode: "on",
    strategy_version: "v14",
    ticket_sol: "0.05",
    max_open: 3,
    markets_enabled: 4,
    open: [
      {
        market: "UNIUSDT",
        mint8: "7xKXtg2C",
        entry_at: "2026-09-19T18:00:00Z",
        sol_spent: "0.05",
        mark_sol: "0.052",
        r_now: "0.4",
        age_s: 1200,
        horizon_s: 14400,
        mark_stale_s: null,
      },
    ],
    signals_seen: 23,
    admitted: 5,
    refused_by_reason: { spot1_open_cap: 3, signal_stale: 2 },
    exits_by_reason: { stop: 2, target: 1 },
    blocked_exits: { abc12345: "panic_slippage_cap" },
    closed: {
      n: 15,
      sum_r_gross: "14.9",
      sum_r_net: "3.2",
      sum_pnl_sol: "0.08",
      expectancy_r_net: "0.21",
    },
    refutation: { trades: 15, threshold: 20, state: "ok" },
    last_signature: "5sigNatureLongEnoughToTruncate",
    last_refusal: "signal_stale",
    last_entries_tick_at: "2026-09-19T18:05:00Z",
    last_exits_tick_at: "2026-09-19T18:05:03Z",
    ...overrides,
  };
}

describe("Spot1Panel", () => {
  it("renders a quiet honest state when spot1 is null (old executor)", () => {
    render(<Spot1Panel spot1={null} />);
    expect(screen.getByText("Mesa spot/1 — ainda não ligada")).toBeInTheDocument();
  });

  it("renders the same quiet state when spot1 is undefined", () => {
    render(<Spot1Panel spot1={undefined} />);
    expect(screen.getByText("Mesa spot/1 — ainda não ligada")).toBeInTheDocument();
  });

  it("renders a full spot1 payload: mode, open position, closed stats, refutation, footer", () => {
    render(<Spot1Panel spot1={spot1()} />);
    expect(screen.getByText("ligada")).toBeInTheDocument();
    expect(screen.getByText("UNIUSDT")).toBeInTheDocument();
    expect(screen.getByText("+0.40R")).toBeInTheDocument();
    expect(screen.getByText("+3.20R")).toBeInTheDocument();
    expect(screen.getByText("stop (R ≤ -1) × 2")).toBeInTheDocument();
    const meter = screen.getByRole("progressbar", { name: "Progresso até a regra de refutação" });
    expect(meter).toHaveAttribute("aria-valuenow", "75");
    expect(screen.getByText(/última assinatura/)).toBeInTheDocument();
    expect(screen.getByText(/entradas em/)).toBeInTheDocument();
  });

  it("names an inert/refused/blocked mode instead of a bare code", () => {
    render(<Spot1Panel spot1={spot1({ mode: "inert:disabled" })} />);
    expect(screen.getByText("inerte: disabled")).toBeInTheDocument();
  });

  it("shows the no-positions-open note without inventing a row", () => {
    render(<Spot1Panel spot1={spot1({ open: [] })} />);
    expect(screen.getByText("Nenhuma posição spot/1 aberta agora.")).toBeInTheDocument();
  });
});
