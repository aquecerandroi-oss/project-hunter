import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// `CandlesChart` never touches money math with these mocks -- it only feeds
// coordinates to the charting library, which is exactly what's replaced
// here (docs/DESIGN.md tokens are exercised via real `getComputedStyle`,
// jsdom supports custom properties set on `documentElement.style`).
const { createChartMock, addSeriesMock, setDataMock, removeMock, chartApplyOptionsMock, seriesApplyOptionsMock } = vi.hoisted(
  () => ({
    createChartMock: vi.fn(),
    addSeriesMock: vi.fn(),
    setDataMock: vi.fn(),
    removeMock: vi.fn(),
    chartApplyOptionsMock: vi.fn(),
    seriesApplyOptionsMock: vi.fn(),
  }),
);

vi.mock("lightweight-charts", () => ({
  CandlestickSeries: "candlestick-series-type",
  createChart: createChartMock,
}));

afterEach(cleanup);

import { CandlesChart } from "@/components/markets/candles-chart";
import type { Candle } from "@/lib/api/types";

const oneCandle: Candle[] = [
  {
    open_time: "2026-09-05T00:00:00Z",
    close_time: "2026-09-05T00:01:00Z",
    open: "65000.00",
    high: "65100.00",
    low: "64900.00",
    close: "65050.00",
    volume: "12.5",
    quote_volume: "812500",
    trade_count: 42,
    taker_buy_volume: "6.25",
  },
];

function makeChart() {
  return {
    addSeries: addSeriesMock,
    applyOptions: chartApplyOptionsMock,
    remove: removeMock,
  };
}

beforeEach(() => {
  createChartMock.mockReset().mockImplementation(() => makeChart());
  addSeriesMock.mockReset().mockReturnValue({ setData: setDataMock, applyOptions: seriesApplyOptionsMock });
  setDataMock.mockReset();
  removeMock.mockReset();
  chartApplyOptionsMock.mockReset();
  seriesApplyOptionsMock.mockReset();
  document.documentElement.removeAttribute("data-theme");
  document.documentElement.style.cssText = "";
});

describe("CandlesChart: mounts even when it first renders with zero candles (F1)", () => {
  it("does not create a chart while there are no candles, but creates one once real candles arrive", async () => {
    const { rerender } = render(<CandlesChart candles={[]} />);
    expect(screen.getByText(/Sem candles ainda/)).toBeInTheDocument();
    expect(createChartMock).not.toHaveBeenCalled();

    rerender(<CandlesChart candles={oneCandle} />);

    await waitFor(() => expect(createChartMock).toHaveBeenCalledTimes(1));
    expect(setDataMock).toHaveBeenCalled();
  });

  it("tears the chart instance down on unmount (no leaked instance)", async () => {
    const { unmount } = render(<CandlesChart candles={oneCandle} />);
    await waitFor(() => expect(createChartMock).toHaveBeenCalledTimes(1));
    unmount();
    expect(removeMock).toHaveBeenCalledTimes(1);
  });
});

describe("CandlesChart: an init failure is an honest, distinct state (F4)", () => {
  it("shows a failure message -- not a blank div, not the 'no candles yet' message", async () => {
    createChartMock.mockImplementation(() => {
      throw new Error("canvas unsupported");
    });

    render(<CandlesChart candles={oneCandle} />);

    await waitFor(() => expect(screen.getByText(/Gráfico indisponível/)).toBeInTheDocument());
    expect(screen.queryByText(/Sem candles ainda/)).not.toBeInTheDocument();
  });
});

describe("CandlesChart: colors track the live theme, not just the one at mount (F5)", () => {
  it("re-applies chart and series colors when data-theme changes, without hardcoded hex", async () => {
    document.documentElement.style.setProperty("--color-gold", "#111111");
    document.documentElement.style.setProperty("--color-red", "#222222");
    document.documentElement.style.setProperty("--color-fg-muted", "#333333");
    document.documentElement.style.setProperty("--color-border", "#444444");

    render(<CandlesChart candles={oneCandle} />);
    await waitFor(() => expect(createChartMock).toHaveBeenCalledTimes(1));
    expect(addSeriesMock).toHaveBeenCalledWith(
      "candlestick-series-type",
      expect.objectContaining({ upColor: "#111111", downColor: "#222222" }),
    );

    // The initial mount's own resize handler already calls
    // `chart.applyOptions(...)` once (`{ width: ... }`) -- capture that call
    // count so the assertion below can prove the THEME CHANGE causes an
    // additional, distinctly-shaped call, not just satisfy `toHaveBeenCalled()`
    // with the resize call already on record before the theme ever changes
    // (H10: the previous version of this test would still pass if the
    // theme-recoloring effect were deleted entirely).
    const callsBeforeThemeChange = chartApplyOptionsMock.mock.calls.length;

    document.documentElement.style.setProperty("--color-gold", "#999999");
    document.documentElement.style.setProperty("--color-red", "#888888");
    document.documentElement.style.setProperty("--color-fg-muted", "#777777");
    document.documentElement.style.setProperty("--color-border", "#666666");
    act(() => {
      document.documentElement.setAttribute("data-theme", "light");
    });

    await waitFor(() =>
      expect(seriesApplyOptionsMock).toHaveBeenCalledWith(expect.objectContaining({ upColor: "#999999", downColor: "#888888" })),
    );
    // The chart itself is never torn down/recreated for a theme change -- only re-colored.
    expect(createChartMock).toHaveBeenCalledTimes(1);
    // A real new call, AFTER the theme change, carrying the NEW tokens --
    // not the resize call's `{ width }` shape, and not merely "called at
    // some point since the mock was created".
    expect(chartApplyOptionsMock.mock.calls.length).toBeGreaterThan(callsBeforeThemeChange);
    const lastCall = chartApplyOptionsMock.mock.calls.at(-1)?.[0];
    expect(lastCall).toMatchObject({
      layout: { textColor: "#777777" },
      grid: { vertLines: { color: "#666666" }, horzLines: { color: "#666666" } },
    });
  });
});
