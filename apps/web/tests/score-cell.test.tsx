import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ScoreCell } from "@/components/radar/score-cell";

afterEach(() => {
  cleanup();
});

const FIRST_SEEN = "2026-09-06T08:00:00Z";

describe("ScoreCell: change sign, color and the two zeros (new episode vs stable)", () => {
  it("shows an explicit '+' sign and the positive semantic color for a positive change", () => {
    render(<ScoreCell score="72.50" change="3.25" firstSeenAt={FIRST_SEEN} lastUpdatedAt="2026-09-06T09:00:00Z" />);
    const changeEl = screen.getByText("+3.25");
    expect(changeEl).toBeInTheDocument();
    expect(changeEl.className).toContain("text-green");
    expect(changeEl.className).not.toContain("text-red");
  });

  it("shows the raw negative sign (no double sign) and the negative semantic color for a negative change", () => {
    render(<ScoreCell score="58.10" change="-4.40" firstSeenAt={FIRST_SEEN} lastUpdatedAt="2026-09-06T09:00:00Z" />);
    const changeEl = screen.getByText("-4.40");
    expect(changeEl).toBeInTheDocument();
    expect(changeEl.className).toContain("text-red");
    expect(changeEl.className).not.toContain("text-green");
  });

  it("labels change=0 as 'novo episódio' only when first_seen_at and last_updated_at are (near) the same instant", () => {
    render(<ScoreCell score="50.00" change="0" firstSeenAt={FIRST_SEEN} lastUpdatedAt="2026-09-06T08:00:02Z" />);
    expect(screen.getByText("novo episódio")).toBeInTheDocument();
    expect(screen.queryByText("sem mudança desde a última leitura")).not.toBeInTheDocument();
  });

  it("labels change=0 as 'sem mudança desde a última leitura' for a mature, stable episode (history exists)", () => {
    render(<ScoreCell score="50.00" change="0" firstSeenAt={FIRST_SEEN} lastUpdatedAt="2026-09-06T10:30:00Z" />);
    expect(screen.getByText("sem mudança desde a última leitura")).toBeInTheDocument();
    expect(screen.queryByText("novo episódio")).not.toBeInTheDocument();
  });

  it("shows an explicit unavailable reason for change=null, never a fabricated zero", () => {
    render(<ScoreCell score="50.00" change={null} firstSeenAt={FIRST_SEEN} lastUpdatedAt="2026-09-06T10:30:00Z" />);
    expect(screen.getByText("mudança indisponível")).toBeInTheDocument();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });
});
