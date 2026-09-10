import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ManualOrderDecisionCard } from "@/components/portfolio/manual-order-decision-card";
import type { RiskDecision } from "@/lib/api/manual-orders-types";

afterEach(cleanup);

const BASE: Omit<RiskDecision, "approved" | "checks" | "sizing"> = {
  kind: "entry",
  proposal_id: "p-1",
  portfolio_id: "w-1",
  market: { exchange: "binance", symbol: "BTCUSDT", market_type: "spot", base_asset: "BTC", quote_asset: "USDT" },
  limits_profile: "paper_v1",
  effective_kill_switch: "ACTIVE",
  cancel_pending: false,
  shadow_only: false,
};

describe("ManualOrderDecisionCard: limitante vencedor, tamanho e motivo de recusa in the vocabulary of docs/RISK_ENGINE.md", () => {
  it("shows the approved size and the winning ceiling (binding_constraint) in Portuguese", () => {
    const decision: RiskDecision = {
      ...BASE,
      approved: true,
      checks: [{ name: "kill_switch", state: "passed", value: null, limit: null, message: "" }],
      sizing: {
        entry_ref: "65000.0000000000",
        sizing_price: "65000.0000000000",
        stop: "63700.0000000000",
        stop_distance_pct: "0.0200000000",
        cost_pct: "0.0010000000",
        caps: [],
        binding_limit: { name: "risk_per_trade", notional: "999.70", limit: "0.0025", detail: "" },
        binding_constraint: "risk_per_trade",
        size_without_multipliers: { name: "sem_multiplicadores" },
        size_without_participation: { name: "sem_participacao" },
        tied_limits: [],
        notional_before_multiplier: "999.70",
        kill_switch_multiplier: "1.0000000000",
        notional_after_multiplier: "999.70",
        qty: "0.0153800000",
        notional: "999.7000000000",
        planned_risk_quote: "25.0000000000",
        planned_risk_pct: "0.0025000000",
      },
    };

    render(<ManualOrderDecisionCard decision={decision} />);

    expect(screen.getByText("Aprovada")).toBeInTheDocument();
    expect(screen.getByText("Risco por operação")).toBeInTheDocument(); // limitCapLabel("risk_per_trade")
    expect(screen.getByText(/999\.70 USDT/)).toBeInTheDocument();
  });

  it("shows the rejection reason(s) in Portuguese for a refused decision, never a raw check name", () => {
    const decision: RiskDecision = {
      ...BASE,
      approved: false,
      checks: [
        { name: "kill_switch", state: "passed", value: null, limit: null, message: "" },
        { name: "stop_distance", state: "failed", value: "0.05", limit: "0.03", message: "fora do teto de distância" },
      ],
      sizing: null,
    };

    render(<ManualOrderDecisionCard decision={decision} />);

    expect(screen.getByText("Recusada")).toBeInTheDocument();
    expect(screen.getByText(/Motivo da recusa: Distância do stop/)).toBeInTheDocument();
    expect(screen.queryByText(/stop_distance/)).not.toBeInTheDocument();
  });

  it("names when the market stays shadow-only for lack of a validated beta", () => {
    const decision: RiskDecision = {
      ...BASE,
      approved: false,
      shadow_only: true,
      checks: [{ name: "beta_validity", state: "unavailable", value: null, limit: null, message: "sem beta validado" }],
      sizing: null,
    };

    render(<ManualOrderDecisionCard decision={decision} />);
    expect(screen.getByText(/Sem β validado/)).toBeInTheDocument();
  });
});
