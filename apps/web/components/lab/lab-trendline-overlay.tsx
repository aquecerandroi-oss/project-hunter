"use client";

import {
  CandlestickSeries,
  createChart,
  createSeriesMarkers,
  LineSeries,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type SeriesMarker,
  type TickMarkType,
  type Time,
} from "lightweight-charts";
import { useEffect, useRef, useState } from "react";

import { EXIT_REASON_LABEL } from "@/components/lab/lab-format";
import type { Candle } from "@/lib/api/types";
import type { OutcomeResult } from "@/lib/api/lab-types";
import { chartColor } from "@/lib/charts/css-var";
import {
  buildHorizontalSegments,
  buildUsedLineSegments,
  candleTimes,
  markerIndexNear,
  pivotBarIndex,
  toCandleSeries,
} from "@/lib/charts/lab-trendline-series";
import { eventKindLabel, lineKindLabel, type TrendlineGeometry } from "@/lib/lab-trendline";
import { logger } from "@/lib/logger";
import { formatBrasiliaTick, formatBrasiliaWithUtcTooltip } from "@/lib/time";

export interface LabTrendlineOverlayProps {
  candles: Candle[];
  geometry: TrendlineGeometry;
  decisionBarClose: string;
  entryPrice: string | null;
  entryTs: string | null;
  stop: string | null;
  target1: string | null;
  exitPrice: string | null;
  exitTs: string | null;
  result: OutcomeResult;
}

const CHART_HEIGHT = 320;
const DASHED = 2;
const SOLID = 0;

type ThemeName = "dark" | "light";

function readTheme(): ThemeName {
  if (typeof document === "undefined") return "dark";
  return document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
}

function useThemeAttribute(): ThemeName {
  const [theme, setTheme] = useState<ThemeName>(readTheme);
  useEffect(() => {
    const observer = new MutationObserver(() => setTheme(readTheme()));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, []);
  return theme;
}

function chartLayoutOptions() {
  return {
    layout: { background: { color: "transparent" as const }, textColor: chartColor("--color-fg-muted") },
    grid: { vertLines: { color: chartColor("--color-border") }, horzLines: { color: chartColor("--color-border") } },
  };
}

function candleSeriesOptions() {
  const green = chartColor("--color-green");
  const red = chartColor("--color-red");
  return { upColor: green, borderUpColor: green, wickUpColor: green, downColor: red, borderDownColor: red, wickDownColor: red };
}

function brasiliaTickMarkFormatter(time: Time, tickMarkType: TickMarkType): string {
  return formatBrasiliaTick(time as number, tickMarkType);
}

function brasiliaCrosshairLabel(time: Time): string {
  return formatBrasiliaWithUtcTooltip(new Date((time as number) * 1000).toISOString());
}

const EXIT_MARKER_COLOR_VAR: Record<OutcomeResult, string> = {
  target: "--color-green",
  stop: "--color-red",
  invalidated: "--color-warning",
  expired: "--color-info",
  open: "--color-fg-muted",
};

/** The used-line solid segment plus its dashed extension, drawn directly onto `chart` -- split out of `buildOverlay` purely to stay under the statement-count lint budget. */
function drawUsedLine(chart: IChartApi, props: LabTrendlineOverlayProps, times: readonly number[]): string[] {
  const usedSegments = buildUsedLineSegments(times as never, props.geometry, props.decisionBarClose, props.exitTs);
  const lineLabel = `${lineKindLabel(props.geometry.lineKind)} (${eventKindLabel(props.geometry.eventKind)}, ${props.geometry.touches ?? "?"} toques)`;
  if (usedSegments.used) {
    const used = chart.addSeries(LineSeries, { color: chartColor("--color-gold"), lineWidth: 2, lineStyle: SOLID, title: lineLabel });
    used.setData(usedSegments.used as never);
  }
  if (usedSegments.extension) {
    const ext = chart.addSeries(LineSeries, { color: chartColor("--color-gold"), lineWidth: 2, lineStyle: DASHED, title: `${lineLabel} (extensão)` });
    ext.setData(usedSegments.extension as never);
  }
  return usedSegments.notes;
}

const LEVEL_COLOR_VAR: Record<string, string> = { Entrada: "--color-info", Stop: "--color-red", Alvo: "--color-green" };

/** Entry/stop/target as bounded segments, drawn directly onto `chart` -- split out of `buildOverlay` purely to stay under the statement-count lint budget. */
function drawLevels(chart: IChartApi, props: LabTrendlineOverlayProps, times: readonly number[]): string[] {
  const { segments, notes } = buildHorizontalSegments(times as never, props.entryTs, props.exitTs, [
    { label: "Entrada", price: props.entryPrice },
    { label: "Stop", price: props.stop },
    { label: "Alvo", price: props.target1 },
  ]);
  for (const segment of segments) {
    const series = chart.addSeries(LineSeries, { color: chartColor(LEVEL_COLOR_VAR[segment.label] ?? "--color-fg-muted"), lineWidth: 2, lineStyle: SOLID, title: segment.label });
    series.setData(segment.points as never);
  }
  return notes;
}

/** Pivot + exit markers -- split out of `buildOverlay` purely to stay under the statement-count lint budget. */
function buildMarkers(props: LabTrendlineOverlayProps, times: readonly number[]): { markers: SeriesMarker<Time>[]; notes: string[] } {
  const markers: SeriesMarker<Time>[] = [];
  const notes: string[] = [];

  if (props.geometry.pivotLowIdx !== null) {
    const pivotIdx = pivotBarIndex(times as never, props.geometry, props.decisionBarClose);
    if (pivotIdx !== null) {
      markers.push({ time: times[pivotIdx] as Time, position: "belowBar", shape: "arrowUp", color: chartColor("--color-warning"), text: `pivô ${props.geometry.pivotLowPrice ?? "?"}` });
    } else {
      notes.push("candles reais não cobrem o pivô -- marcador do pivô não desenhado");
    }
  }

  if (props.exitPrice !== null && props.exitTs !== null) {
    const exitIdx = markerIndexNear(times as never, props.exitTs);
    if (exitIdx !== null) {
      markers.push({
        time: times[exitIdx] as Time,
        position: props.result === "target" ? "belowBar" : "aboveBar",
        shape: "circle",
        color: chartColor(EXIT_MARKER_COLOR_VAR[props.result]),
        text: `saída: ${EXIT_REASON_LABEL[props.result]}`,
      });
    } else {
      notes.push("candles reais não cobrem a saída -- marcador de saída não desenhado");
    }
  }

  return { markers, notes };
}

/** Every line/marker this chart can draw, computed once per render from the same `times` array the candlestick series owns (T3.31 -- see `lib/charts/lab-trendline-series.ts`). Every added `LineSeries` lives and dies with `chart` itself (the effect's own cleanup calls `chart.remove()`), so nothing here needs its own ref. */
function buildOverlay(chart: IChartApi, props: LabTrendlineOverlayProps, times: readonly number[]) {
  const notes = [...drawUsedLine(chart, props, times), ...drawLevels(chart, props, times)];
  const { markers, notes: markerNotes } = buildMarkers(props, times);
  return { markers, notes: [...notes, ...markerNotes] };
}

/** Creates the chart, the candlestick series and the whole overlay -- split out of the creation effect purely to stay under the statement-count lint budget. May throw (the caller's `try` handles it, same convention as every other chart in this app). */
function initializeChart(container: HTMLDivElement, props: LabTrendlineOverlayProps, candleData: ReturnType<typeof toCandleSeries>) {
  const chart = createChart(container, {
    height: CHART_HEIGHT,
    timeScale: { timeVisible: true, secondsVisible: false, tickMarkFormatter: brasiliaTickMarkFormatter },
    localization: { timeFormatter: brasiliaCrosshairLabel },
    ...chartLayoutOptions(),
  });
  const candleSeries = chart.addSeries(CandlestickSeries, candleSeriesOptions());
  candleSeries.setData(candleData);
  const times = candleTimes(candleData);
  const overlay = buildOverlay(chart, props, times);
  const markersApi = createSeriesMarkers(candleSeries, overlay.markers);
  return { chart, candleSeries, markersApi, notes: overlay.notes };
}

/**
 * The operation-detail overlay (brief T3.49): 15m candles plus the exact
 * trend line `trendline_breakout_v1` used for its decision (solid up to the
 * decision bar, dashed to the exit), the stop pivot, entry/stop/target as
 * bounded segments and the exit marker. Every element is drawn only when its
 * own data is both present and covered by the fetched candles -- an absent
 * element is never fabricated, only named in the caption below the chart.
 */
export function LabTrendlineOverlay(props: LabTrendlineOverlayProps) {
  const [container, setContainer] = useState<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const [failed, setFailed] = useState(false);
  const [notes, setNotes] = useState<string[]>([]);
  const theme = useThemeAttribute();

  const candleData = toCandleSeries(props.candles);

  function clearRefs(): void {
    chartRef.current = null;
    candleSeriesRef.current = null;
    markersRef.current = null;
  }

  useEffect(() => {
    if (!container || candleData.length === 0) return undefined;
    let disposed = false;
    let chart: IChartApi | undefined;
    try {
      const built = initializeChart(container, props, candleData);
      chart = built.chart;
      candleSeriesRef.current = built.candleSeries;
      markersRef.current = built.markersApi;
      // eslint-disable-next-line react-hooks/set-state-in-effect -- reflects the real outcome of building the overlay from this render's own props, not a value re-derived on every render
      setNotes(built.notes);
    } catch (error) {
      logger.warn("lab_trendline_overlay_init_failed", { error: String(error) });
      chart?.remove();
      clearRefs();
      setFailed(true);
      return undefined;
    }
    chartRef.current = chart;
    setFailed(false);
    const resize = () => {
      if (disposed) return;
      chart?.applyOptions({ width: container.clientWidth });
    };
    resize();
    window.addEventListener("resize", resize);
    return () => {
      disposed = true;
      window.removeEventListener("resize", resize);
      chart?.remove();
      clearRefs();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- (re)built once per mount/candle-set change; a theme flip is handled by the effect below without a full teardown
  }, [container, candleData.length]);

  useEffect(() => {
    const chart = chartRef.current;
    const candleSeries = candleSeriesRef.current;
    if (!chart || !candleSeries) return;
    chart.applyOptions(chartLayoutOptions());
    candleSeries.applyOptions(candleSeriesOptions());
  }, [theme]);

  if (props.candles.length === 0) {
    return <p className="flex h-[320px] items-center justify-center text-sm text-fg-muted">Sem candles reais para desenhar esta operação.</p>;
  }

  if (failed) {
    return (
      <div className="flex h-[320px] flex-col items-center justify-center gap-1 text-center text-sm">
        <p className="text-fg">Gráfico indisponível.</p>
        <p className="text-fg-muted">As candles chegaram, mas o gráfico não pôde ser desenhado. Recarregue a página.</p>
      </div>
    );
  }

  return (
    <div className="rounded-md border border-border p-4">
      <h4 className="text-sm font-semibold text-fg">Linha usada na decisão</h4>
      <div ref={setContainer} className="mt-3 w-full" />
      {notes.length > 0 && (
        <ul className="mt-2 flex flex-col gap-0.5 text-[11px] text-fg-subtle">
          {notes.map((note) => (
            <li key={note}>· {note}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
