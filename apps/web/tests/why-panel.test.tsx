import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api/opportunities-actions", () => ({ loadOpportunityDetailAction: vi.fn() }));

afterEach(cleanup);

import { WhyPanel } from "@/components/opportunities/why-panel";
import { makeOpportunityAnomaly, makeOpportunityDetail, makeRegime } from "@/tests/fixtures/radar";

describe("WhyPanel: score/direction summary and component contributions", () => {
  it("shows score, confidence, direction and the explanation's real pt-BR resumo", () => {
    render(<WhyPanel detail={makeOpportunityDetail()} currentRegime={null} orgId="org-1" />);
    // "70.00" also appears in the history list below (the newest sample
    // matches the current score in this fixture) -- at least one match is
    // the summary's big number.
    expect(screen.getAllByText("70.00").length).toBeGreaterThan(0);
    expect(screen.getByText("Long")).toBeInTheDocument();
    expect(screen.getByText(/Score 70,00 de 100/)).toBeInTheDocument();
  });

  it("draws a component's contribution bar with its real weight/normalized/contribution", () => {
    render(<WhyPanel detail={makeOpportunityDetail()} currentRegime={null} orgId="org-1" />);
    expect(screen.getByText("momentum")).toBeInTheDocument();
    expect(screen.getByText(/normalizado 80.0000 · contribuiu 16.0000 pontos/)).toBeInTheDocument();
  });

  it("never draws an unavailable component as if it were observed at zero -- shows its real reason instead of a bar", () => {
    render(<WhyPanel detail={makeOpportunityDetail()} currentRegime={null} orgId="org-1" />);
    expect(screen.getByText(/sem dado \(no_usable_input\)/)).toBeInTheDocument();
  });

  it("shows Early-Movement's signed contribution separately from the weighted component list", () => {
    render(<WhyPanel detail={makeOpportunityDetail()} currentRegime={null} orgId="org-1" />);
    expect(screen.getByText(/Early-Movement/)).toBeInTheDocument();
    expect(screen.getByText(/\+2\.5000/)).toBeInTheDocument();
  });
});

describe("WhyPanel: anomalies -- unknown evaluation state never reads as resolved", () => {
  it("shows an active + unknown anomaly with both chips, never collapsed into one label", () => {
    const detail = makeOpportunityDetail({ anomalies: [makeOpportunityAnomaly({ status: "active", evaluation_state: "unknown" })] });
    render(<WhyPanel detail={detail} currentRegime={null} orgId="org-1" />);
    expect(screen.getByText("ativa")).toBeInTheDocument();
    expect(screen.getByText("avaliação desconhecida")).toBeInTheDocument();
    expect(screen.queryByText("resolvida")).not.toBeInTheDocument();
  });

  it("shows the honest empty state when there are no linked anomalies", () => {
    const detail = makeOpportunityDetail({ anomalies: [] });
    render(<WhyPanel detail={detail} currentRegime={null} orgId="org-1" />);
    expect(screen.getByText(/Nenhuma anomalia ativa ligada/)).toBeInTheDocument();
  });
});

describe("WhyPanel: regime with is_stale and UNKNOWN honesty", () => {
  it("shows 'stale' when the matched /regime row says so", () => {
    const detail = makeOpportunityDetail({ regime_id: "55555555-5555-5555-5555-555555555555" });
    render(<WhyPanel detail={detail} currentRegime={makeRegime({ is_stale: true })} orgId="org-1" />);
    expect(screen.getByText("stale")).toBeInTheDocument();
  });

  it("names why the regime is UNKNOWN, never a bare label", () => {
    const detail = makeOpportunityDetail({ regime_id: "55555555-5555-5555-5555-555555555555" });
    render(
      <WhyPanel
        detail={detail}
        currentRegime={makeRegime({ regime: "UNKNOWN", supporting_features: { motivo: "warmup" } })}
        orgId="org-1"
      />,
    );
    expect(screen.getByText(/Motivo:/)).toBeInTheDocument();
  });

  it("says the regime was not confirmed rather than silently treating it as fresh when no /regime row matches", () => {
    const detail = makeOpportunityDetail({ regime_id: "55555555-5555-5555-5555-555555555555" });
    render(<WhyPanel detail={detail} currentRegime={null} orgId="org-1" />);
    expect(screen.getByText(/não confirmado na leitura atual/)).toBeInTheDocument();
  });
});

describe("WhyPanel: feature_snapshot -- nulls carry a reason, never a bare zero", () => {
  it("shows an unavailable feature's value as '—' with its real reason, never '0'", () => {
    render(<WhyPanel detail={makeOpportunityDetail()} currentRegime={null} orgId="org-1" />);
    expect(screen.getByText("relative_volume_1h")).toBeInTheDocument();
    expect(screen.getByText("warmup")).toBeInTheDocument();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });
});

describe("WhyPanel: score history sparkline + list", () => {
  it("lists every history point with its own score and status", () => {
    render(<WhyPanel detail={makeOpportunityDetail()} currentRegime={null} orgId="org-1" />);
    expect(screen.getByText(/últimas 2 amostras/)).toBeInTheDocument();
    expect(screen.getByText("65.00")).toBeInTheDocument();
  });
});

describe("WhyPanel: collapsed technical footer", () => {
  it("carries baseline_ids and weights_version inside a collapsed <details>", () => {
    render(<WhyPanel detail={makeOpportunityDetail()} currentRegime={null} orgId="org-1" />);
    const footer = screen.getByText("Rodapé técnico").closest("details");
    expect(footer).not.toHaveAttribute("open");
    expect(screen.getByText("33333333-3333-3333-3333-333333333333")).toBeInTheDocument();
  });
});
