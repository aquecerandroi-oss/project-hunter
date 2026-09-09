import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { loadLabSignalEnvelopeActionMock, loadLabTrendlineCandlesActionMock, createChartMock, addSeriesMock, createSeriesMarkersMock } = vi.hoisted(() => ({
  loadLabSignalEnvelopeActionMock: vi.fn(),
  loadLabTrendlineCandlesActionMock: vi.fn(),
  createChartMock: vi.fn(),
  addSeriesMock: vi.fn(),
  createSeriesMarkersMock: vi.fn(),
}));

vi.mock("@/lib/api/lab-actions", () => ({
  loadLabSignalEnvelopeAction: loadLabSignalEnvelopeActionMock,
  loadLabTrendlineCandlesAction: loadLabTrendlineCandlesActionMock,
}));

vi.mock("lightweight-charts", () => ({
  CandlestickSeries: "candlestick-series-type",
  LineSeries: "line-series-type",
  createChart: createChartMock,
  createSeriesMarkers: createSeriesMarkersMock,
}));

afterEach(cleanup);

import { LabSignalDetail, type LabSignalDetailProps } from "@/components/lab/lab-signal-detail";
import { exampleTrendlineSupportingFeatures, EXAMPLE_TRENDLINE_OPERATION } from "@/tests/fixtures/lab-trendline";

const OP = EXAMPLE_TRENDLINE_OPERATION;

function baseProps(overrides: Partial<LabSignalDetailProps> = {}): LabSignalDetailProps {
  return {
    signalId: "sig-1",
    market: OP.symbol,
    strategyVersionId: "sv-1",
    cohort: "prospective",
    decisionBarClose: OP.decisionBarClose,
    entryPrice: OP.virtualEntry,
    entryTs: OP.entryTs,
    stop: OP.stop,
    target1: OP.target1,
    exitPrice: OP.exitPrice,
    exitTs: OP.exitTs,
    result: OP.result,
    ...overrides,
  };
}

beforeEach(() => {
  loadLabSignalEnvelopeActionMock.mockReset();
  loadLabTrendlineCandlesActionMock.mockReset();
  createChartMock.mockReset().mockImplementation(() => ({ addSeries: addSeriesMock, applyOptions: vi.fn(), remove: vi.fn() }));
  addSeriesMock.mockReset().mockReturnValue({ setData: vi.fn(), applyOptions: vi.fn() });
  createSeriesMarkersMock.mockReset().mockReturnValue({ setMarkers: vi.fn() });
});

describe("LabSignalDetail -> 'Ver linha de tendência' (brief T3.49): its own independent on-demand fetch", () => {
  it("shows the honest 'esta versão não lê linhas' message for a strategy whose envelope has no line_id", async () => {
    loadLabSignalEnvelopeActionMock.mockResolvedValue({ ok: true, envelope: { features: [{ name: "rsi_14", value: "62.3" }] } });
    render(<LabSignalDetail {...baseProps()} />);

    fireEvent.click(screen.getByRole("button", { name: "Ver linha de tendência" }));

    expect(await screen.findByText(/Esta versão não lê linhas de tendência/)).toBeInTheDocument();
    expect(loadLabTrendlineCandlesActionMock).not.toHaveBeenCalled();
  });

  it("fetches candles with a real historical window and renders the overlay + Geometria panel when the envelope carries a line", async () => {
    loadLabSignalEnvelopeActionMock.mockResolvedValue({ ok: true, envelope: exampleTrendlineSupportingFeatures() });
    loadLabTrendlineCandlesActionMock.mockResolvedValue({
      ok: true,
      derived: true,
      candles: [{ open_time: OP.decisionBarClose, close_time: OP.decisionBarClose, open: "1", high: "1", low: "1", close: "1", volume: "1" }],
    });

    render(<LabSignalDetail {...baseProps()} />);
    fireEvent.click(screen.getByRole("button", { name: "Ver linha de tendência" }));

    await waitFor(() => expect(loadLabTrendlineCandlesActionMock).toHaveBeenCalledTimes(1));
    const [market, beforeIso, limit] = loadLabTrendlineCandlesActionMock.mock.calls[0] as [string, string, number];
    expect(market).toBe(OP.symbol);
    expect(new Date(beforeIso).getTime()).toBeGreaterThan(new Date(OP.exitTs).getTime());
    expect(limit).toBeGreaterThan(0);

    expect(await screen.findByText("Geometria da linha")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ocultar linha de tendência" })).toBeInTheDocument();
    // T3.49 finding: `candles.timeframe = '15m'` has zero rows anywhere in this system -- `derived: true` says so on screen.
    expect(screen.getByText(/Candles agregadas de 1m real/)).toBeInTheDocument();
  });

  it("shows the honest error reason instead of a blank panel when the envelope fetch fails", async () => {
    loadLabSignalEnvelopeActionMock.mockResolvedValue({ ok: false, envelope: null, reason: "sinal não encontrado nesta página" });
    render(<LabSignalDetail {...baseProps()} />);

    fireEvent.click(screen.getByRole("button", { name: "Ver linha de tendência" }));

    expect(await screen.findByText(/sinal não encontrado nesta página/)).toBeInTheDocument();
  });

  it("shows the honest error reason when the candle fetch fails", async () => {
    loadLabSignalEnvelopeActionMock.mockResolvedValue({ ok: true, envelope: exampleTrendlineSupportingFeatures() });
    loadLabTrendlineCandlesActionMock.mockResolvedValue({ ok: false, candles: [], reason: "mercado ambíguo ou não encontrado" });
    render(<LabSignalDetail {...baseProps()} />);

    fireEvent.click(screen.getByRole("button", { name: "Ver linha de tendência" }));

    expect(await screen.findByText(/mercado ambíguo ou não encontrado/)).toBeInTheDocument();
  });

  it("does not call the trendline actions before the button is clicked (unrelated to the existing JSON toggle)", () => {
    render(<LabSignalDetail {...baseProps()} />);
    expect(loadLabSignalEnvelopeActionMock).not.toHaveBeenCalled();
    expect(loadLabTrendlineCandlesActionMock).not.toHaveBeenCalled();
  });
});
