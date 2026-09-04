import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

afterEach(cleanup);

import { EmptyStateCard } from "@/components/dashboard/empty-state-card";
import { MembersCard } from "@/components/dashboard/members-card";
import { OrganizationCard } from "@/components/dashboard/organization-card";
import { WorkspaceCard } from "@/components/dashboard/workspace-card";
import type { OrganizationOut, WorkspaceOut } from "@/lib/api/types";

const organization: OrganizationOut = {
  id: "org-1",
  slug: "acme",
  name: "Acme Capital",
  plan: "FREE",
  kill_switch_state: "ACTIVE",
  created_at: "2026-01-01T00:00:00Z",
};

const workspace: WorkspaceOut = {
  id: "ws-1",
  organization_id: "org-1",
  name: "Main",
  objective: "paper_trading",
  default_risk_profile_id: null,
  settings: {
    default_initial_capital: "10000",
    monitored_exchanges: ["binance"],
    risk_preset: "balanced",
  },
  created_at: "2026-01-01T00:00:00Z",
  onboarding_completed_at: "2026-01-01T00:00:00Z",
};

function hasNoPnlOrFakeNumbers(container: HTMLElement): void {
  const text = container.textContent ?? "";
  expect(text).not.toMatch(/PnL/i);
  expect(text).not.toMatch(/lucro/i);
  expect(text).not.toMatch(/\$[1-9]\d{2,},\d{3}/); // no six/seven-figure fake balances
}

describe("dashboard cards: honest content only", () => {
  it("OrganizationCard renders name, plan and role -- no PnL or invented numbers", () => {
    const { container } = render(<OrganizationCard organization={organization} role="OWNER" />);
    expect(screen.getByText("Acme Capital")).toBeInTheDocument();
    expect(screen.getByText("FREE")).toBeInTheDocument();
    expect(screen.getByText(/Seu papel: OWNER/)).toBeInTheDocument();
    hasNoPnlOrFakeNumbers(container);
  });

  it("WorkspaceCard renders onboarding-derived settings from workspace.settings", () => {
    const { container } = render(<WorkspaceCard workspace={workspace} />);
    expect(screen.getByText("Paper Trading")).toBeInTheDocument();
    expect(screen.getByText("$10,000.00")).toBeInTheDocument();
    expect(screen.getByText("balanced")).toBeInTheDocument();
    expect(screen.getByText("Binance")).toBeInTheDocument();
    hasNoPnlOrFakeNumbers(container);
  });

  it("WorkspaceCard shows an honest placeholder when settings are still empty", () => {
    const empty: WorkspaceOut = { ...workspace, settings: {} };
    render(<WorkspaceCard workspace={empty} />);
    expect(screen.getByText("Nenhuma")).toBeInTheDocument();
  });

  it("MembersCard shows a real count, never a fabricated one", () => {
    render(<MembersCard orgSlug="acme" count={3} atLeast={false} />);
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("MembersCard marks the count as a floor when the page was capped", () => {
    render(<MembersCard orgSlug="acme" count={200} atLeast={true} />);
    expect(screen.getByText("200+")).toBeInTheDocument();
  });

  it("EmptyStateCard for markets states the real M0 reality: zero, and when data arrives", () => {
    render(<EmptyStateCard title="Mercados" message="Mercados monitorados: 0 · dados de mercado chegam no Milestone 1" />);
    expect(screen.getByText(/Mercados monitorados: 0/)).toBeInTheDocument();
    expect(screen.queryByText(/PnL/i)).not.toBeInTheDocument();
  });

  it("EmptyStateCard for portfolio never invents a balance", () => {
    const { container } = render(<EmptyStateCard title="Portfolio" message="Nenhum portfolio ainda · Milestone 3" />);
    expect(screen.getByText(/Nenhum portfolio ainda/)).toBeInTheDocument();
    hasNoPnlOrFakeNumbers(container);
  });
});
