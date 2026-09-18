/**
 * "Carteira real" (T4.57): the panel's honest states -- no `summary` yet
 * (heartbeat/API unavailable), a healthy snapshot with no positions today,
 * and a missing FX quote that must never block the SOL/USD totals.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { WalletSummaryView } from "@/components/meme-live/wallet-summary-view";
import type { WalletSummary } from "@/lib/api/meme-live-wallet-types";

afterEach(cleanup);

const AS_OF = "2026-09-18T18:00:00Z";

function summary(overrides: Partial<WalletSummary> = {}): WalletSummary {
  return {
    label: "REAL",
    server_now: AS_OF,
    executor_status: "alive",
    now: {
      wallet_sol_balance: "1.5",
      wallet_sol_balance_reason: null,
      wallet_balance_stale_s: "2.0",
      wallet_usdc_balance: "10.0",
      wallet_usdc_balance_reason: null,
      sol_usd: { price_usd: "150.0", source: "jupiter", observed_at: AS_OF, origin: "worker_heartbeat" },
      sol_usd_reason: null,
      fx: { usd_brl: "5.4", observed_at: AS_OF, source: "frankfurter.dev", stale: false, reason: null },
      total_usd: "235.0",
      total_usd_reason: null,
      total_brl: "1269.0",
      total_brl_reason: null,
      open_positions: 0,
      open_marked_sol: "0",
      open_unmarked_positions: 0,
      reserve_sol: "1.5",
      reserve_sol_reason: null,
    },
    today: {
      day: "2026-09-18",
      bought: 0,
      sold: 0,
      won: 0,
      lost: 0,
      realized_pnl_sol: "0",
      realized_pnl_brl: "0",
      realized_pnl_brl_reason: null,
      open_pnl_sol: null,
      open_pnl_sol_reason: "no_open_positions",
      fees_sol: "0",
      rent_sol: "0",
      treasury_swaps: 0,
      treasury_usdc_spent: "0",
      treasury_sol_bought: "0",
      daily_loss_sol: "0",
      daily_loss_cap_sol: "0.1",
      daily_loss_reason: null,
      small_test_remaining_sol: "0.05",
    },
    all_time: {
      total_bought: 0,
      total_won: 0,
      total_lost: 0,
      total_pnl_sol: null,
      total_pnl_sol_reason: "no_closed_positions",
      total_pnl_brl: null,
      total_pnl_brl_reason: "no_closed_positions",
      best_trade: null,
      worst_trade: null,
      starting_equity_sol: null,
      starting_equity_source: null,
      starting_equity_at: null,
      starting_equity_reason: "no_starting_equity_reading",
    },
    closed_today: [],
    open: [],
    ...overrides,
  };
}

describe("WalletSummaryView", () => {
  it("shows a loading note before the first poll ever lands", () => {
    render(<WalletSummaryView summary={null} reason={null} />);
    expect(screen.getByText("Carregando a carteira real...")).toBeInTheDocument();
  });

  it("shows the honest failure when there is no summary and a poll failed", () => {
    render(<WalletSummaryView summary={null} reason="Redis indisponível" />);
    expect(screen.getByText("Carteira indisponível: Redis indisponível")).toBeInTheDocument();
  });

  it("keeps the last good snapshot on screen and notes a later failed poll apart from it", () => {
    render(<WalletSummaryView summary={summary()} reason="erro desconhecido" />);
    expect(screen.getByText(/Falha na última atualização/)).toBeInTheDocument();
    expect(screen.getByText("Carteira real")).toBeInTheDocument();
  });

  it("names no positions today and no open positions as two distinct empty states", () => {
    render(<WalletSummaryView summary={summary()} reason={null} />);
    expect(screen.getByText("Nenhuma posição fechada hoje.")).toBeInTheDocument();
    expect(screen.getByText("Nenhuma posição real aberta agora.")).toBeInTheDocument();
  });

  it("never blocks the SOL/USD totals on a missing FX quote, and names it apart from the USD total", () => {
    render(
      <WalletSummaryView
        summary={summary({
          now: {
            ...summary().now,
            total_brl: null,
            total_brl_reason: "no_fx_quote",
            fx: { usd_brl: null, observed_at: null, source: null, stale: false, reason: "no_fx_quote" },
          },
        })}
        reason={null}
      />,
    );
    expect(screen.getByText("$235.00")).toBeInTheDocument();
    expect(screen.getByText("sem câmbio USD/BRL")).toBeInTheDocument();
  });

  it("never invents a wallet balance when the heartbeat never read one", () => {
    render(
      <WalletSummaryView
        summary={summary({
          now: { ...summary().now, wallet_sol_balance: null, wallet_sol_balance_reason: "no_wallet_balance", reserve_sol: null, reserve_sol_reason: "no_wallet_balance" },
        })}
        reason={null}
      />,
    );
    expect(screen.getAllByText("sem leitura da carteira").length).toBeGreaterThan(0);
  });
});
