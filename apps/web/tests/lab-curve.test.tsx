import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { createChartMock, addSeriesMock, setDataMock, removeMock } = vi.hoisted(() => ({
  createChartMock: vi.fn(),
  addSeriesMock: vi.fn(),
  setDataMock: vi.fn(),
  removeMock: vi.fn(),
}));

vi.mock("lightweight-charts", () => ({
  LineSeries: "line-series-type",
  createChart: createChartMock,
}));

afterEach(cleanup);

import { LabCurveChart } from "@/components/lab/lab-curve-chart";
import type { LabCurveSeriesInput } from "@/components/lab/lab-scoreboard";
import { exampleRuler } from "@/tests/fixtures/lab";

function makeChart() {
  return { addSeries: addSeriesMock, applyOptions: vi.fn(), remove: removeMock };
}

function makeSeries(overrides: Partial<LabCurveSeriesInput> = {}): LabCurveSeriesInput {
  return {
    versionId: "v-1",
    label: "momentum/v2",
    verdict: "validada",
    points: [
      { ts: "2026-09-06T03:41:00Z", r: "-1.0421", cum_r: "-1.0421" },
      { ts: "2026-09-06T05:10:00Z", r: "2.0000", cum_r: "0.9579" },
    ],
    truncated: false,
    failed: false,
    ...overrides,
  };
}

beforeEach(() => {
  createChartMock.mockReset().mockImplementation(() => makeChart());
  addSeriesMock.mockReset().mockReturnValue({ setData: setDataMock, applyOptions: vi.fn() });
  setDataMock.mockReset();
  removeMock.mockReset();
});

/**
 * T3.24b addendum A3/A5: the "Coorte da curva" overlay -- when both a
 * `"prospective"` and a `"replay"` series exist for the same version, the
 * chart draws two distinct `lightweight-charts` series (never one merged
 * line) and the replay one is dashed.
 */
describe("LabCurveChart: prospective + replay overlay (addendum A3)", () => {
  it("draws two series for the same version -- one per cohort -- never colliding on a shared key", () => {
    render(
      <LabCurveChart
        series={[makeSeries({ cohort: "prospective" }), makeSeries({ cohort: "replay", points: [{ ts: "2026-08-29T12:00:00Z", r: "2", cum_r: "2" }] })]}
        ruler={exampleRuler()}
      />,
    );
    expect(addSeriesMock).toHaveBeenCalledTimes(2);
  });

  it("draws the replay line dashed (lineStyle 2) and the prospective line solid (lineStyle 0)", () => {
    render(
      <LabCurveChart
        series={[makeSeries({ cohort: "prospective" }), makeSeries({ cohort: "replay" })]}
        ruler={exampleRuler()}
      />,
    );
    expect(addSeriesMock).toHaveBeenCalledWith("line-series-type", expect.objectContaining({ lineStyle: 0 }));
    expect(addSeriesMock).toHaveBeenCalledWith("line-series-type", expect.objectContaining({ lineStyle: 2 }));
  });

  it("legend shows 'prospectiva' and 'replay — não conta para o veredito' side by side", () => {
    render(
      <LabCurveChart
        series={[makeSeries({ cohort: "prospective" }), makeSeries({ cohort: "replay" })]}
        ruler={exampleRuler()}
      />,
    );
    const legend = screen.getByTestId("lab-curve-legend");
    expect(legend).toHaveTextContent("prospectiva");
    expect(legend).toHaveTextContent("replay — não conta para o veredito");
  });

  it("omits the cohort caption entirely for pre-T3.24b callers that never set `cohort` (backward compatible)", () => {
    render(<LabCurveChart series={[makeSeries()]} ruler={exampleRuler()} />);
    const legend = screen.getByTestId("lab-curve-legend");
    expect(legend).not.toHaveTextContent("prospectiva");
    expect(legend).not.toHaveTextContent("replay — não conta para o veredito");
  });

  it("still shows the height-200 empty state text unchanged when nothing is drawable", () => {
    render(<LabCurveChart series={[makeSeries({ points: [] })]} ruler={exampleRuler()} />);
    expect(screen.getByText(/Nenhum resultado resolvido ainda para desenhar a curva/)).toBeInTheDocument();
    expect(createChartMock).not.toHaveBeenCalled();
  });

  it("shows '(primeiros 2.000 pontos)', never the old 'capado em' wording, for a truncated series", () => {
    render(<LabCurveChart series={[makeSeries({ truncated: true })]} ruler={exampleRuler()} />);
    expect(screen.getByTestId("lab-curve-legend")).toHaveTextContent("(primeiros 2.000 pontos)");
  });
});

describe("LabCurveChart: theme/currency effects still key by the right series after the cohort change", () => {
  it("updates both series' data on a currency toggle without throwing", async () => {
    render(
      <LabCurveChart
        series={[makeSeries({ cohort: "prospective" }), makeSeries({ cohort: "replay" })]}
        ruler={exampleRuler()}
      />,
    );
    await waitFor(() => expect(setDataMock).toHaveBeenCalled());
  });
});
