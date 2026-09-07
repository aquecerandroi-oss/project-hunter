import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { PortfolioResultCard } from "@/components/portfolio/portfolio-result-card";
import { makeAnchor, makeSummary } from "@/tests/fixtures/portfolio";

afterEach(cleanup);

describe("PortfolioResultCard: opening / operational / currency / total, split apart", () => {
  it("renders the four decomposition lines with their real values", () => {
    render(<PortfolioResultCard summary={makeSummary()} anchor={makeAnchor()} />);
    expect(screen.getByText("R$ 100.000,00")).toBeInTheDocument(); // opening
    expect(screen.getByText("+R$ 540,00")).toBeInTheDocument(); // operational
    expect(screen.getByText("+R$ 185,19")).toBeInTheDocument(); // currency
    expect(screen.getByText("+R$ 725,19")).toBeInTheDocument(); // total
    expect(screen.getByText("R$ 100.725,19")).toBeInTheDocument(); // current equity
  });

  it("shows both the opening and the current rate, each with its own source and instant", () => {
    render(<PortfolioResultCard summary={makeSummary()} anchor={makeAnchor()} />);
    expect(screen.getByText(/5\.4000000000 BRL\/USDT/)).toBeInTheDocument();
    expect(screen.getByText(/5\.4100000000 BRL\/USDT/)).toBeInTheDocument();
    expect(screen.getAllByText(/binance\.spot\.ticker/).length).toBeGreaterThanOrEqual(2);
  });

  it("never renders a null BRL decomposition as R$ 0,00 -- shows the named reason instead", () => {
    render(
      <PortfolioResultCard
        summary={makeSummary({ brl: null, brl_unavailable_reason: "fx_rejected", brl_unavailable_detail: "rate 999 outside [1, 100]" })}
        anchor={makeAnchor()}
      />,
    );
    expect(screen.queryByText("R$ 0,00")).not.toBeInTheDocument();
    expect(screen.getByText(/cotação mais recente foi recusada/)).toBeInTheDocument();
    expect(screen.getByText(/rate 999 outside \[1, 100\]/)).toBeInTheDocument();
  });

  it("still names an uncatalogued BRL reason rather than hiding it", () => {
    render(<PortfolioResultCard summary={makeSummary({ brl: null, brl_unavailable_reason: "some_new_reason" })} anchor={makeAnchor()} />);
    expect(screen.getByText(/motivo não catalogado: some_new_reason/)).toBeInTheDocument();
  });
});
