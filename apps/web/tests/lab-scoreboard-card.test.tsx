import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { LabScoreboardCard } from "@/components/lab/lab-scoreboard-card";
import { LabScoreboardEmpty } from "@/components/lab/lab-scoreboard-empty";
import { LabScoreboardSection } from "@/components/lab/lab-scoreboard-section";
import { exampleRuler, exampleScoreboardRow } from "@/tests/fixtures/lab";

afterEach(cleanup);

describe("LabScoreboardCard: identity, verdict, maturity bar, money and the research toggle (brief T3.18 item 3)", () => {
  it("shows the version identity, purpose chip, status and since-date", () => {
    render(<LabScoreboardCard row={exampleScoreboardRow()} ruler={exampleRuler()} />);
    expect(screen.getByText("momentum/v2")).toBeInTheDocument();
    expect(screen.getByText("paper")).toBeInTheDocument();
    expect(screen.getByText("ativa")).toBeInTheDocument();
    // Brief T3.22: Brasília, not UTC -- the fixture's `activated_at` crosses
    // midnight backward into the previous Brasília day.
    expect(screen.getByText("desde 05/09/2026")).toBeInTheDocument();
  });

  it("shows the verdict as a dominant chip with the maturity bar next to it", () => {
    render(<LabScoreboardCard row={exampleScoreboardRow()} ruler={exampleRuler()} />);
    expect(screen.getByText("validada")).toBeInTheDocument();
    expect(screen.getByText("112 de 100 resultados · 34 de 30 dias")).toBeInTheDocument();
  });

  it("shows money through the T3.17 ruler by default (always visible, no toggle needed)", () => {
    render(<LabScoreboardCard row={exampleScoreboardRow()} ruler={exampleRuler()} />);
    expect(screen.getByText("Resultado acumulado (simulado)")).toBeInTheDocument();
    expect(screen.getByText("Média por operação (simulado)")).toBeInTheDocument();
    expect(screen.getAllByText(/^\+.*USDT$/).length).toBeGreaterThan(0);
  });

  it("hides the research units behind 'Detalhes de pesquisa' until toggled", () => {
    render(<LabScoreboardCard row={exampleScoreboardRow()} ruler={exampleRuler()} />);
    expect(screen.queryByTestId("lab-scoreboard-research")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Detalhes de pesquisa" }));
    const research = screen.getByTestId("lab-scoreboard-research");
    expect(research).toHaveTextContent("58.93% (33/56)");
    expect(research).toHaveTextContent("0.1834R");
    expect(research).toHaveTextContent("1.4200");
    expect(research).toHaveTextContent("4 perdas seguidas");
    expect(research).toHaveTextContent("6.1200R");

    fireEvent.click(screen.getByRole("button", { name: "Ocultar detalhes de pesquisa" }));
    expect(screen.queryByTestId("lab-scoreboard-research")).not.toBeInTheDocument();
  });

  it("shows why there is no evaluable result yet instead of a fabricated zero (brief item 3: 'all pending')", () => {
    const row = exampleScoreboardRow({
      evaluable: 0,
      pending: 5,
      emitted: 5,
      no_entry: 0,
      censored: 0,
      verdict: "inconclusivo",
      maturity: { evaluable: 0, days: 0, threshold: { outcomes: 100, days: 30 }, mature: false },
    });
    render(<LabScoreboardCard row={row} ruler={exampleRuler()} />);
    expect(screen.getByText(/ainda sem resultado avaliável \(5 emitidos\): 5 pendentes/)).toBeInTheDocument();
    expect(screen.queryByText("Resultado acumulado (simulado)")).not.toBeInTheDocument();
  });

  it("always states the mechanical rule next to the verdict (brief item 5)", () => {
    render(<LabScoreboardCard row={exampleScoreboardRow()} ruler={exampleRuler()} />);
    expect(screen.getByText("régua: 100 resultados e 30 dias; validada = expectancy > 0 e PF > 1")).toBeInTheDocument();
  });
});

describe("LabScoreboardSection: ordering and the whole-board empty state", () => {
  it("orders active first then by sum_r, rendering one card per row", () => {
    const worseActive = exampleScoreboardRow({
      version: { ...exampleScoreboardRow().version, id: "v-worse", version: "v1" },
      sum_r: { value: "1", reason: null, count: 1, ordered_by: "exit_ts" },
    });
    const betterActive = exampleScoreboardRow({
      version: { ...exampleScoreboardRow().version, id: "v-better", version: "v2" },
      sum_r: { value: "20", reason: null, count: 1, ordered_by: "exit_ts" },
    });
    render(<LabScoreboardSection rows={[worseActive, betterActive]} ruler={exampleRuler()} />);
    const cards = screen.getAllByTestId("lab-scoreboard-card");
    expect(cards).toHaveLength(2);
    expect(cards[0]).toHaveTextContent("momentum/v2");
    expect(cards[1]).toHaveTextContent("momentum/v1");
  });

  it("shows the honest 'no version emitted yet' state, never an error, for an empty scoreboard", () => {
    render(<LabScoreboardSection rows={[]} ruler={exampleRuler()} />);
    expect(screen.getByText("Nenhuma versão do Lab emitiu sinal ainda.")).toBeInTheDocument();
  });
});

describe("LabScoreboardEmpty", () => {
  it("renders standalone", () => {
    render(<LabScoreboardEmpty />);
    expect(screen.getByText("Nenhuma versão do Lab emitiu sinal ainda.")).toBeInTheDocument();
  });
});
