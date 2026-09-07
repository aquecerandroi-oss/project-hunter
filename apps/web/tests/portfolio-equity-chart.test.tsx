import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { createChartMock, addSeriesMock, setDataMock, setMarkersMock, removeMock } = vi.hoisted(() => ({
  createChartMock: vi.fn(),
  addSeriesMock: vi.fn(),
  setDataMock: vi.fn(),
  setMarkersMock: vi.fn(),
  removeMock: vi.fn(),
}));

vi.mock("lightweight-charts", () => ({
  LineSeries: "line-series-type",
  createChart: createChartMock,
  createSeriesMarkers: vi.fn(() => ({ setMarkers: setMarkersMock })),
}));

afterEach(cleanup);

import { PortfolioEquityChart } from "@/components/portfolio/portfolio-equity-chart";
import { makeEquityPoint } from "@/tests/fixtures/portfolio";

function makeChart() {
  return { addSeries: addSeriesMock, applyOptions: vi.fn(), remove: removeMock };
}

beforeEach(() => {
  createChartMock.mockReset().mockImplementation(() => makeChart());
  addSeriesMock.mockReset().mockReturnValue({ setData: setDataMock, applyOptions: vi.fn() });
  setDataMock.mockReset();
  setMarkersMock.mockReset();
  removeMock.mockReset();
});

describe("PortfolioEquityChart: honest empty/failed states", () => {
  it("shows an honest empty state and never creates a chart with zero points", () => {
    render(<PortfolioEquityChart points={[]} asOf="2026-09-07T12:00:00Z" />);
    expect(screen.getByText(/Sem pontos na curva de patrimônio ainda/)).toBeInTheDocument();
    expect(createChartMock).not.toHaveBeenCalled();
  });

  it("shows a distinct failure message when the charting library throws", async () => {
    createChartMock.mockImplementation(() => {
      throw new Error("canvas unsupported");
    });
    render(<PortfolioEquityChart points={[makeEquityPoint()]} asOf="2026-09-07T12:00:00Z" />);
    await waitFor(() => expect(screen.getByText(/Gráfico indisponível/)).toBeInTheDocument());
  });
});

describe("PortfolioEquityChart: USDT/BRL toggle, gaps never invented", () => {
  it("plots USDT by default and switches to BRL (with a gap, marked) on toggle", async () => {
    const points = [makeEquityPoint({ ts: "2026-09-07T10:00:00Z", equity: "100", brl_equity: "540" }), makeEquityPoint({ ts: "2026-09-07T11:00:00Z", equity: "110", brl_equity: null, brl_unavailable_reason: "no_fx_observation" })];
    render(<PortfolioEquityChart points={points} asOf="2026-09-07T12:00:00Z" />);

    await waitFor(() => expect(setDataMock).toHaveBeenCalled());
    const firstCallData = setDataMock.mock.calls[0]?.[0] as { value?: number }[];
    expect(firstCallData.map((d) => d.value)).toEqual([100, 110]);

    fireEvent.click(screen.getByRole("button", { name: "BRL" }));

    await waitFor(() => expect(setDataMock).toHaveBeenCalledTimes(2));
    const brlData = setDataMock.mock.calls[1]?.[0] as { value?: number }[];
    // Second point has no `value` at all (a genuine gap), never a 0 or the USDT figure re-labeled.
    expect(brlData[0]?.value).toBe(540);
    expect(brlData[1]).not.toHaveProperty("value");

    expect(setMarkersMock).toHaveBeenLastCalledWith([expect.objectContaining({ text: "sem BRL" })]);
    expect(screen.getByText(/1 sem leitura BRL/)).toBeInTheDocument();
  });
});
