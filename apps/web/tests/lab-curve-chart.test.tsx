import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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

describe("LabCurveChart: honest empty/failed states (brief T3.18 item 4)", () => {
  it("shows an honest empty state and never creates a chart when no version has a resolved outcome", () => {
    render(<LabCurveChart series={[makeSeries({ points: [] })]} ruler={exampleRuler()} />);
    expect(screen.getByText(/Nenhum resultado resolvido ainda para desenhar a curva/)).toBeInTheDocument();
    expect(createChartMock).not.toHaveBeenCalled();
  });

  it("shows a distinct failure message when the charting library throws", async () => {
    createChartMock.mockImplementation(() => {
      throw new Error("canvas unsupported");
    });
    render(<LabCurveChart series={[makeSeries()]} ruler={exampleRuler()} />);
    await waitFor(() => expect(screen.getByText(/Gráfico indisponível/)).toBeInTheDocument());
  });
});

describe("LabCurveChart: one line per version, USDT by default with an R toggle", () => {
  it("plots cumulative result in USDT through the ruler, then raw R on toggle", async () => {
    const ruler = exampleRuler();
    render(<LabCurveChart series={[makeSeries()]} ruler={ruler} />);

    await waitFor(() => expect(setDataMock).toHaveBeenCalled());
    const usdtData = setDataMock.mock.calls[0]?.[0] as { value?: number }[];
    expect(usdtData[0]?.value).toBeCloseTo(-1.0421 * ruler.riskUsdt, 6);
    expect(usdtData[1]?.value).toBeCloseTo(0.9579 * ruler.riskUsdt, 6);

    fireEvent.click(screen.getByRole("button", { name: "R" }));
    await waitFor(() => expect(setDataMock).toHaveBeenCalledTimes(2));
    const rData = setDataMock.mock.calls[1]?.[0] as { value?: number }[];
    expect(rData[0]?.value).toBe(-1.0421);
    expect(rData[1]?.value).toBe(0.9579);
  });

  it("colours each line by its own verdict (brief item 4: 'same colours as the cards')", () => {
    render(<LabCurveChart series={[makeSeries({ verdict: "reprovada" })]} ruler={exampleRuler()} />);
    expect(addSeriesMock).toHaveBeenCalledWith("line-series-type", expect.objectContaining({ lineWidth: 2 }));
  });

  it("legend shows the version label, its verdict chip, and marks a failed/truncated/empty series honestly", () => {
    render(
      <LabCurveChart
        series={[
          makeSeries({ versionId: "v-1", label: "momentum/v2", verdict: "validada" }),
          makeSeries({ versionId: "v-2", label: "momentum/v3", verdict: "inconclusivo", points: [], failed: true }),
          makeSeries({ versionId: "v-3", label: "momentum/v4", verdict: "reprovada", truncated: true }),
        ]}
        ruler={exampleRuler()}
      />,
    );
    const legend = screen.getByTestId("lab-curve-legend");
    expect(legend).toHaveTextContent("momentum/v2");
    expect(legend).toHaveTextContent("curva indisponível: falha ao carregar");
    expect(legend).toHaveTextContent("capado em 2.000 pontos");
  });

  it("never draws a line for a version with no resolved outcome yet, even when another version has one", () => {
    render(<LabCurveChart series={[makeSeries({ versionId: "v-1" }), makeSeries({ versionId: "v-2", points: [] })]} ruler={exampleRuler()} />);
    expect(addSeriesMock).toHaveBeenCalledTimes(1);
  });
});
