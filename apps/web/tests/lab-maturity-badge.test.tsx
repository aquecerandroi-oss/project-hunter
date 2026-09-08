import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { LabMaturityBadge } from "@/components/lab/lab-maturity-badge";
import type { MaturityOut } from "@/lib/api/lab-types";

afterEach(cleanup);

describe("LabMaturityBadge: 'Pesquisa' branch (above the 100 outcomes / 30 days threshold)", () => {
  it("renders 'Pesquisa' (never a promise) with the real counts once maturity.inconclusive is false", () => {
    const maturity: MaturityOut = { evaluable_outcomes: 142, distinct_days: 34, inconclusive: false };
    render(<LabMaturityBadge maturity={maturity} />);

    expect(screen.getByText("Pesquisa")).toBeInTheDocument();
    expect(screen.getByText(/142 resultados avaliáveis, 34 dias distintos/)).toBeInTheDocument();
    expect(screen.getByText(/nunca promessa/)).toBeInTheDocument();
    expect(screen.queryByText(/Inconclusivo/)).not.toBeInTheDocument();
  });
});

describe("LabMaturityBadge: compact mode (brief T3.24b item [4], the <details> summary)", () => {
  it("renders a single line with no subtitle: 'Inconclusivo · 37/100 · 2/30 dias'", () => {
    const maturity: MaturityOut = { evaluable_outcomes: 37, distinct_days: 2, inconclusive: true };
    render(<LabMaturityBadge maturity={maturity} compact />);
    expect(screen.getByText("Inconclusivo · 37/100 · 2/30 dias")).toBeInTheDocument();
    expect(screen.queryByText(/nunca promessa/)).not.toBeInTheDocument();
  });
});
