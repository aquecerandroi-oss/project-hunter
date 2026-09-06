import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { LabVersionCard } from "@/components/lab/lab-version-card";
import { makeVersionSummary } from "@/tests/fixtures/lab";

afterEach(cleanup);

describe("LabVersionCard: honest nulls, always-visible label and 'não aplicável'", () => {
  it("renders the real fixture (copied from contract-S3-lab.md) without crashing", () => {
    render(<LabVersionCard version={makeVersionSummary()} supersededBy={null} />);
    expect(screen.getByText("momentum / v2")).toBeInTheDocument();
  });

  it("shows both portfolio 'não aplicável' lines with their reasons, always -- never omitted", () => {
    render(<LabVersionCard version={makeVersionSummary()} supersededBy={null} />);
    expect(screen.getByText(/PnL de carteira: não aplicável \(not_applicable\)/)).toBeInTheDocument();
    expect(screen.getByText(/Drawdown de carteira: não aplicável \(not_applicable\)/)).toBeInTheDocument();
  });

  it("never renders a null metric as '0' -- shows its reason text instead, scoped to that metric's own cell", () => {
    const version = makeVersionSummary({
      metrics: {
        ...makeVersionSummary().metrics,
        net_profit_rate: { value: null, reason: "no_sample" },
      },
    });
    render(<LabVersionCard version={version} supersededBy={null} />);
    // Scoped to the main metrics grid, not the whole card: `r_ex_funding`
    // reuses the same Portuguese label ("Taxa de lucro líquido") for its own
    // (unaffected, non-null) net_profit_rate, so an unscoped query would
    // match two buttons. Also scoped away from the funnel, where other real
    // counts (e.g. `censored.total: 0`) legitimately render a literal "0" --
    // that is a true count, not a reason standing in for one.
    const mainMetrics = screen.getByTestId("lab-main-metrics");
    const trigger = within(mainMetrics).getByRole("button", { name: "Taxa de lucro líquido" });
    const cell = trigger.closest("div");
    expect(cell).not.toBeNull();
    expect(within(cell as HTMLElement).queryByText("0", { exact: true })).not.toBeInTheDocument();
    expect(within(cell as HTMLElement).getByText(/sem amostra madura/)).toBeInTheDocument();
  });

  it("shows PF's sum_positive/sum_negative_abs/sample_size even when value is null (Astra must-fix 3)", () => {
    const version = makeVersionSummary({
      metrics: {
        ...makeVersionSummary().metrics,
        profit_factor: { value: null, reason: "no_losses", sum_positive: "1.5000", sum_negative_abs: "0", sample_size: 3 },
      },
    });
    render(<LabVersionCard version={version} supersededBy={null} />);
    expect(screen.getByText(/\+1.5000 \/ -0 \(n=3\)/)).toBeInTheDocument();
  });

  it("shows the maturity badge text exactly as specified (brief S3b)", () => {
    render(<LabVersionCard version={makeVersionSummary()} supersededBy={null} />);
    expect(screen.getByText("Inconclusivo · 9 outcomes avaliáveis / 100 · 1 dias distintos / 30")).toBeInTheDocument();
  });

  it("links superseded_by to the target version's in-page anchor, not itself", () => {
    render(
      <LabVersionCard
        version={makeVersionSummary({ strategy_version_id: "v1-id", version: "v1" })}
        supersededBy={{ id: "v2-id", label: "momentum/v2" }}
      />,
    );
    const link = screen.getByRole("link", { name: /substituída por momentum\/v2/ });
    expect(link).toHaveAttribute("href", "#version-v2-id");
  });

  it("renders the r_ex_funding block as its own section, separate from the main metrics", () => {
    render(<LabVersionCard version={makeVersionSummary()} supersededBy={null} />);
    expect(screen.getByText(/r_ex_funding \(mesma população, sem funding\)/)).toBeInTheDocument();
  });
});
