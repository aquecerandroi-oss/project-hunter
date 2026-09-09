import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { RadarCoverageStrip } from "@/components/radar/radar-coverage-strip";
import { makeRadarCoverage, makeRadarDetector } from "@/tests/fixtures/radar-coverage";

afterEach(cleanup);

describe("RadarCoverageStrip", () => {
  it("renders the headline with the real T3.46 numbers, no invented data", () => {
    render(<RadarCoverageStrip coverage={makeRadarCoverage()} />);
    expect(screen.getByText(/cobre 25 de 217 mercados/)).toBeInTheDocument();
    expect(screen.getByText(/maior score já visto 38/)).toBeInTheDocument();
  });

  it("renders all twelve detectors, in plain Portuguese, no raw enum", () => {
    render(<RadarCoverageStrip coverage={makeRadarCoverage()} />);
    expect(screen.getByText("Pico de volume")).toBeInTheDocument();
    expect(screen.getByText("Atividade de baleias")).toBeInTheDocument();
    expect(screen.getAllByText("Produzindo").length).toBe(4);
    expect(screen.getAllByText("Desarmado").length).toBe(3);
    expect(screen.getAllByText("Silencioso — sem motivo declarado").length).toBe(5);
  });

  it("shows the declared reason for a disarmed detector", () => {
    render(<RadarCoverageStrip coverage={makeRadarCoverage()} />);
    expect(screen.getByText("funding indisponível para este mercado")).toBeInTheDocument();
  });

  it("flags the silent-with-no-reason defect explicitly, never hiding it", () => {
    render(<RadarCoverageStrip coverage={makeRadarCoverage()} />);
    expect(screen.getAllByText(/defeito conhecido, não filtro intencional/).length).toBe(5);
  });

  it("renders the three reopen conditions, none met with the real numbers", () => {
    render(<RadarCoverageStrip coverage={makeRadarCoverage()} />);
    expect(screen.getByText("Quando o estudo reabre")).toBeInTheDocument();
    expect(screen.getByText(/Baselines passando o gate v2/)).toBeInTheDocument();
    expect(screen.getByText(/Mercados com alguma anomalia/)).toBeInTheDocument();
    expect(screen.getByText(/Dias de histórico/)).toBeInTheDocument();
  });

  it("renders an honest fallback when the coverage read failed, not a crash or a fabricated strip", () => {
    render(<RadarCoverageStrip coverage={null} />);
    expect(screen.getByText(/Não foi possível ler o estado do Radar agora/)).toBeInTheDocument();
  });

  it("a detector added to the enum with a rows_31d > 0 always reads producing, even if the heartbeat still lists it as disarmed", () => {
    render(
      <RadarCoverageStrip
        coverage={makeRadarCoverage({
          detectors: [makeRadarDetector({ type: "VOLUME_SPIKE", rows_31d: 3, disarmed_reason: "funding_unavailable" })],
        })}
      />,
    );
    expect(screen.getByText("Produzindo")).toBeInTheDocument();
    expect(screen.getByText(/3 anomalias/)).toBeInTheDocument();
  });
});
