import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { PortfolioEmpty } from "@/components/portfolio/portfolio-empty";

afterEach(cleanup);

describe("PortfolioEmpty: no main wallet, honest and inert-button-free", () => {
  it("states plainly that there is no principal wallet yet", () => {
    render(<PortfolioEmpty />);
    expect(screen.getByText(/Nenhuma carteira principal aberta/)).toBeInTheDocument();
  });

  it("never renders a button that pretends to open a wallet", () => {
    render(<PortfolioEmpty />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("names the real operator script instead", () => {
    render(<PortfolioEmpty />);
    expect(screen.getByText(/open_paper_wallet\.py/)).toBeInTheDocument();
  });
});
