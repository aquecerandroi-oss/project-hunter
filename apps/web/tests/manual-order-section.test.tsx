/**
 * T3.72b MEDIUM finding #2: `blockReason`'s priority order -- role (VIEWER)
 * first, then the wallet's own open state, then the kill switch -- each with
 * its own visible reason (never a bare disabled button, `manual-order-
 * section.tsx`'s own docstring).
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/portfolio/manual-order-form", () => ({
  ManualOrderForm: () => null,
}));

import { ManualOrderSection } from "@/components/portfolio/manual-order-section";

const BASE = {
  orgId: "org-1",
  portfolioId: "wallet-1",
  maxStopDistancePct: "0.03",
};

afterEach(cleanup);

describe("ManualOrderSection: blockReason priority", () => {
  it("shows the role reason for a VIEWER, even when the wallet AND the kill switch also block", () => {
    render(
      <ManualOrderSection
        {...BASE}
        canTrade={false}
        walletOpenReason="A carteira não está aberta para receber ordens agora."
        killSwitchReason="Kill switch acionado (blocks_entries) -- novas entradas suspensas."
      >
        <div />
      </ManualOrderSection>,
    );

    const button = screen.getByRole("button", { name: "Nova ordem paper" });
    expect(button).toBeDisabled();
    expect(screen.getByText("Requer o papel Trader ou superior nesta organização.")).toBeInTheDocument();
    expect(screen.queryByText(/carteira não está aberta/)).not.toBeInTheDocument();
    expect(screen.queryByText(/kill switch acionado/i)).not.toBeInTheDocument();
  });

  it("shows the wallet-not-open reason ahead of the kill switch when the trader role is fine", () => {
    render(
      <ManualOrderSection
        {...BASE}
        canTrade
        walletOpenReason="A carteira não está aberta para receber ordens agora."
        killSwitchReason="Kill switch acionado (blocks_entries) -- novas entradas suspensas."
      >
        <div />
      </ManualOrderSection>,
    );

    const button = screen.getByRole("button", { name: "Nova ordem paper" });
    expect(button).toBeDisabled();
    expect(screen.getByText("A carteira não está aberta para receber ordens agora.")).toBeInTheDocument();
    expect(screen.queryByText(/kill switch acionado/i)).not.toBeInTheDocument();
  });

  it("falls through to the kill switch reason once the role and the wallet are both fine", () => {
    render(
      <ManualOrderSection {...BASE} canTrade walletOpenReason={null} killSwitchReason="Kill switch acionado (blocks_entries) -- novas entradas suspensas.">
        <div />
      </ManualOrderSection>,
    );

    const button = screen.getByRole("button", { name: "Nova ordem paper" });
    expect(button).toBeDisabled();
    expect(screen.getByText("Kill switch acionado (blocks_entries) -- novas entradas suspensas.")).toBeInTheDocument();
  });

  it("enables the button with no reason shown once nothing blocks", () => {
    render(
      <ManualOrderSection {...BASE} canTrade walletOpenReason={null} killSwitchReason={null}>
        <div />
      </ManualOrderSection>,
    );

    const button = screen.getByRole("button", { name: "Nova ordem paper" });
    expect(button).toBeEnabled();
    expect(screen.queryByText(/requer o papel trader/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/carteira não está aberta/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/kill switch acionado/i)).not.toBeInTheDocument();
  });
});
