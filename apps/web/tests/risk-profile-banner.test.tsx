import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { RiskProfileBanner } from "@/components/portfolio/risk-profile-banner";

afterEach(cleanup);

describe("RiskProfileBanner (T3.72d): visible, honest, never invented", () => {
  it("renders nothing when the reason is null (profile linked and matching the engine, or read unavailable)", () => {
    render(<RiskProfileBanner reason={null} />);
    expect(screen.queryByTestId("risk-profile-banner")).not.toBeInTheDocument();
  });

  it("shows the exact divergence sentence when given one", () => {
    const reason = "Os limites mostrados não são os que o motor aplica -- perfil divergente; procedimento no ACTIVATION.md §8b.";
    render(<RiskProfileBanner reason={reason} />);
    expect(screen.getByTestId("risk-profile-banner")).toBeInTheDocument();
    expect(screen.getByText(reason)).toBeInTheDocument();
  });

  it("shows the exact missing-link sentence when given one", () => {
    const reason = "Carteira sem perfil de risco vinculado -- o motor não admite entradas até o vínculo (ACTIVATION.md §8b).";
    render(<RiskProfileBanner reason={reason} />);
    expect(screen.getByText(reason)).toBeInTheDocument();
  });
});
