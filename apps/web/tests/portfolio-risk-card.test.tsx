import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { PortfolioRiskCard } from "@/components/portfolio/portfolio-risk-card";
import { makeKillSwitch, makeRiskState } from "@/tests/fixtures/portfolio";

afterEach(cleanup);

describe("PortfolioRiskCard: kill switch BLOQUEADO in destaque, nulls never become 0%", () => {
  it("renders daily loss and drawdown as real percentages when present", () => {
    render(<PortfolioRiskCard riskState={makeRiskState()} killSwitch={makeKillSwitch()} />);
    expect(screen.getByText("-0.50%")).toBeInTheDocument();
    expect(screen.getByText("-1.00%")).toBeInTheDocument();
  });

  it("never shows '0%' for a null daily_loss_pct/drawdown_pct -- shows 'indisponível' with the reason instead", () => {
    render(
      <PortfolioRiskCard
        riskState={makeRiskState({ daily_loss_pct: null, drawdown_pct: null, equity_day_start: null })}
        killSwitch={makeKillSwitch()}
      />,
    );
    expect(screen.queryByText("0%")).not.toBeInTheDocument();
    expect(screen.queryByText("0.00%")).not.toBeInTheDocument();
    expect(screen.getAllByText(/indisponível/).length).toBeGreaterThanOrEqual(3); // daily loss, drawdown, day-start equity
  });

  it("shows the three unmerged scopes and the reason for a real kill switch state", () => {
    render(
      <PortfolioRiskCard
        riskState={makeRiskState()}
        killSwitch={makeKillSwitch({
          effective: "WARNING",
          scopes: { system: "ACTIVE", organization: "ACTIVE", portfolio: "WARNING" },
          reason: "perda diária de 1.20% (limite 1%)",
        })}
      />,
    );
    // "AVISO" now labels both the top-level effective badge and the
    // `portfolio` scope (`killSwitchLabel` reused for scopes, T3.24a) --
    // "ATIVO" labels the other two (unmerged) scopes.
    expect(screen.getAllByText("AVISO").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("perda diária de 1.20% (limite 1%)")).toBeInTheDocument();
    expect(screen.getAllByText("ATIVO").length).toBeGreaterThanOrEqual(2);
  });

  it("puts a TRADING_DISABLED kill switch in visible destaque (its own labeled panel, entries-blocked line, red styling)", () => {
    render(
      <PortfolioRiskCard
        riskState={makeRiskState()}
        killSwitch={makeKillSwitch({ effective: "TRADING_DISABLED", blocks_entries: true, reason: "drawdown de 8.50% (limite 8%)" })}
      />,
    );
    expect(screen.getByText("BLOQUEADO")).toBeInTheDocument();
    expect(screen.getByText("Entradas bloqueadas")).toBeInTheDocument();
    const panel = screen.getByTestId("kill-switch-panel");
    expect(panel.className).toMatch(/border-red/);
  });

  it("shows the last transition's evidence in a technical-detail disclosure", () => {
    render(
      <PortfolioRiskCard
        riskState={makeRiskState()}
        killSwitch={makeKillSwitch({
          last_transition: {
            from_state: "ACTIVE",
            to_state: "WARNING",
            reason: "perda diária de 1.20%",
            actor_type: "system",
            actor_id: null,
            evidence: { daily_loss_pct: "-0.0120000000", limit: "-0.0100000000" },
            created_at: "2026-09-07T09:00:00Z",
          },
        })}
      />,
    );
    expect(screen.getByText(/Última transição: ATIVO → AVISO/)).toBeInTheDocument();
    expect(screen.getByText(/"daily_loss_pct": "-0.0120000000"/)).toBeInTheDocument();
  });

  it("never invents paper_v1's numeric limits -- names only that they don't appear on this screen", () => {
    render(<PortfolioRiskCard riskState={makeRiskState()} killSwitch={makeKillSwitch()} />);
    expect(screen.getByText(/ainda não aparecem nesta tela/)).toBeInTheDocument();
    expect(screen.queryByText(/0,25/)).not.toBeInTheDocument();
    expect(screen.queryByText(/0\.25%/)).not.toBeInTheDocument();
  });

  it("warns when the daily reference is unavailable even though the switch itself reads ACTIVE", () => {
    render(
      <PortfolioRiskCard
        riskState={makeRiskState()}
        killSwitch={makeKillSwitch({
          effective: "ACTIVE",
          blocks_entries: true,
          daily_reference: {
            trading_day: null,
            trading_day_timezone: "America/Sao_Paulo",
            trading_day_start_utc: null,
            equity_day_start: null,
            observed_at: null,
            available: false,
          },
        })}
      />,
    );
    expect(screen.getByText(/Referência do dia indisponível/)).toBeInTheDocument();
  });
});
