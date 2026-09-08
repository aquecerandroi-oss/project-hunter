import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { LabScoreboardCard } from "@/components/lab/lab-scoreboard-card";
import { exampleReplayBlock, exampleReplicationBlock, exampleRuler, exampleScoreboardRow } from "@/tests/fixtures/lab";

afterEach(cleanup);

/**
 * Component-level tests for the Placar's "Replay"/"Replicação" blocks (brief
 * T3.24b addendum A1/A2) -- kept separate from `lab-scoreboard-card.test.tsx`
 * (existing prospective-only coverage), named `lab-scoreboard.test.tsx` per
 * the addendum's own "A5. Testes" list.
 */
describe("LabScoreboardCard: 'Replay' block (addendum A1)", () => {
  it("is absent when row.replay is null", () => {
    render(<LabScoreboardCard row={exampleScoreboardRow({ replay: null })} ruler={exampleRuler()} />);
    expect(screen.queryByTestId("lab-replay-block")).not.toBeInTheDocument();
  });

  it("shows the exact replay label and the four numbers when row.replay is present", () => {
    render(<LabScoreboardCard row={exampleScoreboardRow({ replay: exampleReplayBlock() })} ruler={exampleRuler()} />);
    const block = screen.getByTestId("lab-replay-block");
    expect(within(block).getByText("replay — não conta para o veredito")).toBeInTheDocument();
    expect(within(block).getByText("288")).toBeInTheDocument(); // decisions_simulated
    expect(within(block).getByText("3")).toBeInTheDocument(); // operations_closed
    expect(within(block).getByText("2.00R")).toBeInTheDocument(); // expectancy_r, 2 casas
    expect(within(block).getByText("4.50")).toBeInTheDocument(); // profit_factor, 2 casas
    expect(within(block).getByText(/1 dias · 1 mercados/)).toBeInTheDocument();
  });

  it("never lets a positive replay change the (negative, prospective-only) verdict or maturity", () => {
    const row = exampleScoreboardRow({
      verdict: "inconclusivo",
      expectancy_r: { value: "-0.4362", reason: null },
      maturity: { evaluable: 1, days: 1, threshold: { outcomes: 100, days: 30 }, mature: false },
      replay: exampleReplayBlock(),
    });
    render(<LabScoreboardCard row={row} ruler={exampleRuler()} />);
    expect(screen.getByText("inconclusiva")).toBeInTheDocument();
    expect(screen.queryByText("validada")).not.toBeInTheDocument();
    // The replay block's own positive expectancy is still shown, just never mixed in.
    expect(within(screen.getByTestId("lab-replay-block")).getByText("2.00R")).toBeInTheDocument();
  });
});

describe("LabScoreboardCard: 'Replicação' block (addendum A2)", () => {
  it("is absent when row.replication is null", () => {
    render(<LabScoreboardCard row={exampleScoreboardRow({ replication: null })} ruler={exampleRuler()} />);
    expect(screen.queryByTestId("lab-replication-block")).not.toBeInTheDocument();
  });

  it("shows the pt status label, siblings summary and each arm's evidence", () => {
    render(<LabScoreboardCard row={exampleScoreboardRow({ replication: exampleReplicationBlock() })} ruler={exampleRuler()} />);
    const block = screen.getByTestId("lab-replication-block");
    expect(within(block).getByText("replicando")).toBeInTheDocument();
    expect(within(block).getByText(/irmãs 0\/1 maduras · 0 positivas \(esperado 10, exigido 7\)/)).toBeInTheDocument();
    expect(within(block).getByText("irmã 1 (v2): prospectivo")).toBeInTheDocument();
  });

  it("shows the reason lines with pt labels and the raw code in title", () => {
    render(<LabScoreboardCard row={exampleScoreboardRow({ replication: exampleReplicationBlock() })} ruler={exampleRuler()} />);
    const block = screen.getByTestId("lab-replication-block");
    const bootstrapReason = within(block).getByText(/Bootstrap:/);
    expect(bootstrapReason).toHaveAttribute("title", "amostra_insuficiente: 1 < 20");
  });
});
