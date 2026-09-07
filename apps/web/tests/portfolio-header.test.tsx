import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { PortfolioHeader } from "@/components/portfolio/portfolio-header";
import { makeSummary } from "@/tests/fixtures/portfolio";

afterEach(cleanup);

describe("PortfolioHeader: equity side-by-side in USDT and BRL, never a fabricated BRL number", () => {
  it("renders both the USDT and the BRL equity", () => {
    render(<PortfolioHeader summary={makeSummary()} />);
    expect(screen.getByText("18,650.50 USDT")).toBeInTheDocument();
    expect(screen.getByText("R$ 100.725,19")).toBeInTheDocument();
  });

  it("shows 'não disponível' for BRL, not a $0 or an invented conversion, when brl is null", () => {
    render(<PortfolioHeader summary={makeSummary({ brl: null, brl_unavailable_reason: "no_fx_observation" })} />);
    expect(screen.getByText("não disponível")).toBeInTheDocument();
  });

  it("shows no warning banner when marks are complete and nothing is unavailable", () => {
    render(<PortfolioHeader summary={makeSummary()} />);
    expect(screen.queryByText("Aviso")).not.toBeInTheDocument();
  });

  it("shows a visible warning (not a silent zero) when marks_complete is false", () => {
    render(<PortfolioHeader summary={makeSummary({ marks_complete: false })} />);
    expect(screen.getByText("Aviso")).toBeInTheDocument();
    expect(screen.getByText(/marcações a mercado incompletas/)).toBeInTheDocument();
    // The equity number itself is still shown, never replaced by the warning.
    expect(screen.getByText("18,650.50 USDT")).toBeInTheDocument();
  });

  it("names every unavailable reason from the API, never inventing its own list", () => {
    render(<PortfolioHeader summary={makeSummary({ unavailable: ["daily_reference", "marks"] })} />);
    expect(screen.getByText(/referência do dia/)).toBeInTheDocument();
    expect(screen.getByText(/marcações de alguma posição aberta estão desatualizadas/)).toBeInTheDocument();
  });
});
