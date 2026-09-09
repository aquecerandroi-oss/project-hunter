import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { createChartMock, addSeriesMock, setDataMock, createSeriesMarkersMock, removeMock } = vi.hoisted(() => ({
  createChartMock: vi.fn(),
  addSeriesMock: vi.fn(),
  setDataMock: vi.fn(),
  createSeriesMarkersMock: vi.fn(),
  removeMock: vi.fn(),
}));

vi.mock("lightweight-charts", () => ({
  CandlestickSeries: "candlestick-series-type",
  LineSeries: "line-series-type",
  createChart: createChartMock,
  createSeriesMarkers: createSeriesMarkersMock,
}));

afterEach(cleanup);

import { LabTrendlineOverlay } from "@/components/lab/lab-trendline-overlay";
import { extractTrendlineGeometry } from "@/lib/lab-trendline";
import { exampleTrendlineSupportingFeatures, EXAMPLE_TRENDLINE_OPERATION } from "@/tests/fixtures/lab-trendline";
import type { Candle } from "@/lib/api/types";

const OP = EXAMPLE_TRENDLINE_OPERATION;
const EXTRACTED = extractTrendlineGeometry(exampleTrendlineSupportingFeatures()).geometry;
if (!EXTRACTED) throw new Error("expected the fixture envelope to carry a trend line");
const GEOMETRY = EXTRACTED;

function candleAt(iso: string): Candle {
  return { open_time: iso, close_time: iso, open: "0.075", high: "0.076", low: "0.074", close: "0.0751", volume: "1" } as Candle;
}

/** Every 15m bar from `2026-08-19T14:00:00Z` (before `line_first_idx`, 14:15Z) through `2026-08-20T05:00:00Z` (past the exit, `04:30Z`). */
function realCandles(): Candle[] {
  const start = new Date("2026-08-19T14:00:00Z").getTime();
  const end = new Date("2026-08-20T05:00:00Z").getTime();
  const out: Candle[] = [];
  for (let t = start; t <= end; t += 15 * 60_000) out.push(candleAt(new Date(t).toISOString()));
  return out;
}

function makeChart() {
  return { addSeries: addSeriesMock, applyOptions: vi.fn(), remove: removeMock };
}

beforeEach(() => {
  createChartMock.mockReset().mockImplementation(() => makeChart());
  addSeriesMock.mockReset().mockReturnValue({ setData: setDataMock, applyOptions: vi.fn() });
  setDataMock.mockReset();
  createSeriesMarkersMock.mockReset().mockReturnValue({ setMarkers: vi.fn() });
  removeMock.mockReset();
});

describe("LabTrendlineOverlay: honest empty/failed states", () => {
  it("shows an honest empty state and never creates a chart with zero candles", () => {
    render(
      <LabTrendlineOverlay
        candles={[]}
        geometry={GEOMETRY}
        decisionBarClose={OP.decisionBarClose}
        entryPrice={OP.virtualEntry}
        entryTs={OP.entryTs}
        stop={OP.stop}
        target1={OP.target1}
        exitPrice={OP.exitPrice}
        exitTs={OP.exitTs}
        result={OP.result}
      />,
    );
    expect(screen.getByText(/Sem candles reais para desenhar esta operação/)).toBeInTheDocument();
    expect(createChartMock).not.toHaveBeenCalled();
  });

  it("shows a distinct failure message when the charting library throws", async () => {
    createChartMock.mockImplementation(() => {
      throw new Error("canvas unsupported");
    });
    render(
      <LabTrendlineOverlay
        candles={realCandles()}
        geometry={GEOMETRY}
        decisionBarClose={OP.decisionBarClose}
        entryPrice={OP.virtualEntry}
        entryTs={OP.entryTs}
        stop={OP.stop}
        target1={OP.target1}
        exitPrice={OP.exitPrice}
        exitTs={OP.exitTs}
        result={OP.result}
      />,
    );
    await waitFor(() => expect(screen.getByText(/Gráfico indisponível/)).toBeInTheDocument());
  });
});

describe("LabTrendlineOverlay: draws candles plus the used line, entry/stop/target and the exit marker from real data", () => {
  it("adds a candlestick series and one line series per drawable element (used line + extension + entry + stop + target)", async () => {
    render(
      <LabTrendlineOverlay
        candles={realCandles()}
        geometry={GEOMETRY}
        decisionBarClose={OP.decisionBarClose}
        entryPrice={OP.virtualEntry}
        entryTs={OP.entryTs}
        stop={OP.stop}
        target1={OP.target1}
        exitPrice={OP.exitPrice}
        exitTs={OP.exitTs}
        result={OP.result}
      />,
    );
    await waitFor(() => expect(addSeriesMock).toHaveBeenCalled());
    const calls = addSeriesMock.mock.calls;
    expect(calls.filter((c) => c[0] === "candlestick-series-type")).toHaveLength(1);
    // used line + dashed extension + entry + stop + target = 5 line series.
    expect(calls.filter((c) => c[0] === "line-series-type")).toHaveLength(5);
    expect(createSeriesMarkersMock).toHaveBeenCalled();
    const markers = createSeriesMarkersMock.mock.calls[0]?.[1] as { text: string }[];
    expect(markers.some((m) => m.text.includes("pivô"))).toBe(true);
    expect(markers.some((m) => m.text.includes("saída: invalidada"))).toBe(true);
  });

  it("names the missing element instead of drawing it when the operation never entered", async () => {
    render(
      <LabTrendlineOverlay
        candles={realCandles()}
        geometry={GEOMETRY}
        decisionBarClose={OP.decisionBarClose}
        entryPrice={null}
        entryTs={null}
        stop={OP.stop}
        target1={OP.target1}
        exitPrice={null}
        exitTs={null}
        result="open"
      />,
    );
    expect(await screen.findByText(/sem entrada registrada/)).toBeInTheDocument();
    expect(await screen.findByText(/operação sem saída registrada/)).toBeInTheDocument();
  });
});
