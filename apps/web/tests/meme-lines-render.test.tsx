/**
 * T4.10b render checks: the mcap chart draws the lines (or says why it
 * cannot), the features table shows the line/hype columns with their reasons,
 * and the desk names a probe/scale leg -- all tolerant to the fields not
 * existing yet (the backend lands in parallel).
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { BetLegBadge } from "@/components/meme-desk/bet-leg";
import { MemeCurveChart } from "@/components/meme/meme-curve-chart";
import { MemeFeaturesTable } from "@/components/meme/meme-features-table";
import type { MemeDeskBet } from "@/lib/api/meme-desk-types";
import type { MemeFeaturePoint, MemeSnapshotPoint } from "@/lib/api/meme-types";

afterEach(cleanup);

function snapshot(observedAt: string, mcap: string | null): MemeSnapshotPoint {
  return {
    observed_at: observedAt,
    source: "solana_rpc",
    virtual_sol_reserves: "30",
    virtual_token_reserves: "1000000000",
    real_sol_reserves: "0.5",
    real_token_reserves: "790000000",
    complete: false,
    mcap_sol: mcap,
  };
}

function feature(overrides: Partial<MemeFeaturePoint> & Record<string, unknown> = {}): MemeFeaturePoint {
  return {
    end_time: "2026-09-12T13:30:00Z",
    age_minutes: 12,
    curve_progress_pct: "0.12",
    progress_reason: null,
    mcap_sol: "13",
    curve_reason: null,
    unique_buyers: 8,
    unique_buyers_reason: null,
    buy_sell_ratio: "1.5",
    buy_sell_ratio_reason: null,
    top10_share: null,
    top10_share_reason: "no_holders_reader",
    creator_sold: false,
    creator_sold_reason: null,
    coverage: "1",
    features_version: "meme_features_v3",
    ...overrides,
  };
}

const TRACED = {
  support_line_sol: "10",
  support_line_slope: "0.5",
  high_15m_sol: "12.5",
  low_15m_sol: "7",
  breakout_15m: true,
  higher_lows: true,
  distance_to_support_pct: "0.3",
  line_points: 11,
  line_reason: null,
  hype_score: "0.72",
  hype_reason: null,
};

const SNAPSHOTS = [snapshot("2026-09-12T13:10:00Z", "8"), snapshot("2026-09-12T13:20:00Z", "11"), snapshot("2026-09-12T13:30:00Z", "13")];

describe("MemeCurveChart with lines", () => {
  it("draws the support line, the previous window's high and the breakout mark, and lists them in the caption", () => {
    const { container } = render(<MemeCurveChart snapshots={SNAPSHOTS} features={[feature(TRACED), feature({ ...TRACED, end_time: "2026-09-12T13:29:00Z", high_15m_sol: "12" })]} />);
    expect(container.querySelector('[data-line="support"]')).not.toBeNull();
    expect(container.querySelector('[data-line="previous-high"]')).not.toBeNull();
    expect(container.querySelector('[data-line="breakout"]')).not.toBeNull();
    expect(screen.getByText(/suporte 10\.0000 SOL/)).toBeInTheDocument();
    expect(screen.getByText(/fundos ascendentes: sim/)).toBeInTheDocument();
    expect(screen.getByText(/máxima 15 min anterior 12\.0000 SOL/)).toBeInTheDocument();
  });

  it("says 'linha ainda não traçável: <motivo>' and draws no line when line_reason is set", () => {
    const { container } = render(<MemeCurveChart snapshots={SNAPSHOTS} features={[feature({ ...TRACED, support_line_sol: null, support_line_slope: null, higher_lows: null, breakout_15m: false, line_reason: "too_few_points" })]} />);
    expect(container.querySelector('[data-line="support"]')).toBeNull();
    expect(container.querySelector('[data-line="breakout"]')).toBeNull();
    expect(screen.getByText("linha ainda não traçável: menos de 5 fotografias na janela")).toBeInTheDocument();
  });

  it("says 'linha: sem leitura' when the payload predates the columns, and still draws the curve", () => {
    const { container } = render(<MemeCurveChart snapshots={SNAPSHOTS} features={[feature()]} />);
    expect(container.querySelector("polyline")).not.toBeNull();
    expect(container.querySelector("[data-line]")).toBeNull();
    expect(screen.getByText("linha: sem leitura")).toBeInTheDocument();
  });

  it("keeps the line reading visible even when the curve itself cannot be drawn", () => {
    render(<MemeCurveChart snapshots={[SNAPSHOTS[0] as MemeSnapshotPoint]} features={[feature({ ...TRACED, support_line_sol: null, line_reason: "no_snapshot" })]} />);
    expect(screen.getByText("Sem histórico suficiente para o gráfico de mcap.")).toBeInTheDocument();
    expect(screen.getByText("linha ainda não traçável: sem fotografia da curva na janela")).toBeInTheDocument();
  });
});

describe("MemeFeaturesTable with the line and hype columns", () => {
  it("renders support with its distance, higher lows, breakout and hype per minute", () => {
    render(<MemeFeaturesTable features={[feature(TRACED)]} />);
    expect(screen.getByText("Suporte (SOL)")).toBeInTheDocument();
    expect(screen.getByText("Hype")).toBeInTheDocument();
    expect(screen.getByText("10.0000 SOL")).toBeInTheDocument();
    expect(screen.getByText("+30.00%")).toBeInTheDocument();
    expect(screen.getByText("0.72")).toBeInTheDocument();
    // higher_lows and breakout_15m -- "Sim"/"Não" like the "Dev vendeu" column already reads.
    expect(screen.getAllByText("Sim")).toHaveLength(2);
  });

  it("collapses the three line cells into one named reason when the line is not traceable", () => {
    render(<MemeFeaturesTable features={[feature({ ...TRACED, support_line_sol: null, higher_lows: null, breakout_15m: null, line_reason: "flat", hype_score: null, hype_reason: "no_tape_no_board" })]} />);
    expect(screen.getByText("linha ainda não traçável: sem dois fundos distintos (curva plana)")).toBeInTheDocument();
    expect(screen.getByText("sem hype: sem fita e sem board no minuto")).toBeInTheDocument();
  });

  it("says 'sem leitura' for both when the row predates the columns", () => {
    render(<MemeFeaturesTable features={[feature()]} />);
    expect(screen.getByText("linha: sem leitura")).toBeInTheDocument();
    expect(screen.getByText("hype: sem leitura")).toBeInTheDocument();
  });
});

function bet(extra: Record<string, unknown> = {}): MemeDeskBet {
  return {
    id: "bet-2",
    status: "open",
    mode: "paper",
    entry_at: "2026-09-12T11:51:00Z",
    sol_spent: "0.04",
    fee_sol: null,
    tokens: null,
    initial_risk_sol: "0.04",
    params: { size_sol: "0.04", target_x: "2", trailing_pct: "30", max_hold_s: 900, note: null },
    hold_deadline_at: null,
    mark_sol: null,
    mark_at: null,
    high_water_x: null,
    pnl_sol: null,
    r_multiple: null,
    unrealized_pnl_sol: null,
    unrealized_r: null,
    exit_at: null,
    exit_reason: null,
    sol_received: null,
    sol_usd_at_entry: null,
    sol_usd_at_exit: null,
    ...extra,
  } as MemeDeskBet;
}

describe("BetLegBadge on the desk", () => {
  it("names the hype probe", () => {
    render(<BetLegBadge bet={bet({ leg: "probe", parent_bet_id: null })} knownBetIds={[]} />);
    expect(screen.getByText("semi-comprado (sonda)")).toBeInTheDocument();
  });

  it("names the second leg and links to the parent probe when it is on the page", () => {
    render(<BetLegBadge bet={bet({ leg: "scale", parent_bet_id: "bet-1" })} knownBetIds={["bet-1", "bet-2"]} />);
    expect(screen.getByText("escalado (perna 2)")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /sonda/ })).toHaveAttribute("href", "#bet-bet-1");
  });

  it("shows the parent's short id without a dead link when the probe is not on the page", () => {
    render(<BetLegBadge bet={bet({ leg: "scale", parent_bet_id: "0f1c2d3e-aaaa-bbbb-cccc-000000000000" })} knownBetIds={["bet-2"]} />);
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getByText(/sonda 0f1c2d3e/)).toBeInTheDocument();
  });

  it("renders nothing for a single-leg bet or a payload without the column", () => {
    const { container } = render(
      <>
        <BetLegBadge bet={bet({ leg: "single" })} knownBetIds={[]} />
        <BetLegBadge bet={bet()} knownBetIds={[]} />
      </>,
    );
    expect(container.textContent).toBe("");
  });
});
