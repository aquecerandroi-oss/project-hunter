"use client";

import {
  CandlestickSeries,
  createChart,
  createSeriesMarkers,
  LineSeries,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type MouseEventParams,
  type SeriesMarker,
  type TickMarkType,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useRef, useState } from "react";

import type { DeskPositionOut } from "@/lib/api/market-desk-types";
import type { SignalListItemOut } from "@/lib/api/lab-types";
import type { Candle } from "@/lib/api/types";
import { barIndexContaining } from "@/lib/charts/confluence-series";
import { chartColor } from "@/lib/charts/css-var";
import { sanitizeCandlePoints } from "@/lib/charts/series-data";
import { logger } from "@/lib/logger";
import { formatBrasiliaTick, formatBrasiliaWithUtcTooltip } from "@/lib/time";

export interface ConfluenceChartProps {
  candles: Candle[];
  timeframeSeconds: number;
  /** Real entries/exits whose life overlaps the loaded window (design §3 overlay 3) -- always drawn, gold, time-only (never a price level: `spot/1`'s stop is evaluated in SOL, not on this Binance axis). */
  positions: DeskPositionOut[];
  /** The one signal, if any, whose geometry draws over the price -- design §6: "só o item selecionado desenha sobre o preço". */
  selectedSignal: SignalListItemOut | null;
  onBarClick?: (iso: string) => void;
  onReady?: (chart: IChartApi | null) => void;
  /** Pinged on pan/zoom/resize so `ConfluenceLanes` can recompute its own pixel positions off the same time scale. */
  onRangeChange?: () => void;
}

const CHART_HEIGHT = 320;
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

function layoutOptions() {
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

function toChartData(candles: Candle[]) {
  const raw = candles.map((candle) => ({
    time: Math.floor(new Date(candle.open_time).getTime() / 1000) as UTCTimestamp,
    open: Number(candle.open),
    high: Number(candle.high),
    low: Number(candle.low),
    close: Number(candle.close),
  }));
  return sanitizeCandlePoints(raw);
}

const RESULT_COLOR_VAR: Record<string, string> = {
  target: "--color-green",
  stop: "--color-red",
  invalidated: "--color-warning",
  expired: "--color-info",
  open: "--color-fg-muted",
};

/** Real entry/exit markers -- design §3 overlay 3: gold, time-only, no price level. `label` carries R/PnL when known. */
function buildRealMarkers(times: readonly UTCTimestamp[], positions: readonly DeskPositionOut[], timeframeS: number): { markers: SeriesMarker<Time>[]; notes: string[] } {
  const markers: SeriesMarker<Time>[] = [];
  const notes: string[] = [];
  const gold = chartColor("--color-gold");
  for (const position of positions) {
    const entryIdx = barIndexContaining(times, position.entry_at, timeframeS);
    if (entryIdx === null) notes.push(`entrada real de ${position.entry_at} fora dos candles carregados`);
    else markers.push({ time: times[entryIdx] as Time, position: "belowBar", shape: "circle", color: gold, text: `entrada real${position.r_multiple !== null ? ` (${Number(position.r_multiple).toFixed(2)}R)` : ""}` });

    if (position.exit_at !== null) {
      const exitIdx = barIndexContaining(times, position.exit_at, timeframeS);
      if (exitIdx === null) notes.push(`saída real de ${position.exit_at} fora dos candles carregados`);
      else markers.push({ time: times[exitIdx] as Time, position: "aboveBar", shape: "circle", color: gold, text: `saída real${position.pnl_sol !== null ? ` (${Number(position.pnl_sol) >= 0 ? "+" : ""}${Number(position.pnl_sol).toFixed(4)} SOL)` : ""}` });
    }
  }
  return { markers, notes };
}

/** The selected signal's reference/stop/target lines plus its direction and exit markers -- the only geometry ever drawn over the price (design §3 overlay 1-2, §6). Every `LineSeries` it creates is collected into `series` so the caller can remove them cleanly on the next pass or on de-selection. */
function buildSignalOverlay(chart: IChartApi, times: readonly UTCTimestamp[], signal: SignalListItemOut, timeframeS: number): { markers: SeriesMarker<Time>[]; notes: string[]; series: ISeriesApi<"Line">[] } {
  const notes: string[] = [];
  const markers: SeriesMarker<Time>[] = [];
  const series: ISeriesApi<"Line">[] = [];
  const startIdx = barIndexContaining(times, signal.decision_at, timeframeS);
  if (startIdx === null) {
    notes.push("sinal selecionado fora dos candles carregados -- geometria não desenhada");
    return { markers, notes, series };
  }
  // Astra's review of T4.82 (must-fix 3): a closed signal whose exit bar is
  // NOT covered (a gap, or the exit fell after the fetched window) used to
  // fall back to `times.length - 1` -- silently stretching the reference/
  // stop/target lines past the real exit, into candles that happened after
  // the position was already closed. An open signal (`exit_ts === null`)
  // legitimately draws to the newest loaded bar (design: the geometry is
  // still "live"); a closed one whose exit bar is missing draws nothing past
  // the decision bar instead of guessing how far to stretch.
  const endIdx = signal.exit_ts === null ? times.length - 1 : barIndexContaining(times, signal.exit_ts, timeframeS);
  if (endIdx === null) notes.push("saída do sinal fora dos candles carregados -- linhas não estendidas além da decisão");
  const lo = Math.min(startIdx, endIdx ?? startIdx);
  const hi = Math.max(startIdx, endIdx ?? startIdx);

  function addLevel(price: string | null, colorVar: string, label: string) {
    if (price === null) {
      notes.push(`sem ${label.toLowerCase()} registrado`);
      return;
    }
    const value = Number(price);
    const line = chart.addSeries(LineSeries, { color: chartColor(colorVar), lineWidth: 2, title: label });
    line.setData(times.map((time, index) => (index >= lo && index <= hi ? { time: time as Time, value } : { time: time as Time })));
    series.push(line);
  }

  addLevel(signal.reference_price, "--color-info", "Referência");
  addLevel(signal.stop, "--color-red", "Stop");
  addLevel(signal.target1, "--color-green", "Alvo");

  const directionColorVar = signal.direction === "short" ? "--color-red" : "--color-green";
  markers.push({
    time: times[startIdx] as Time,
    position: signal.direction === "short" ? "aboveBar" : "belowBar",
    shape: signal.direction === "short" ? "arrowDown" : "arrowUp",
    color: chartColor(directionColorVar),
    text: signal.direction,
  });

  if (signal.result !== "open" && signal.exit_ts !== null) {
    const exitIdx = barIndexContaining(times, signal.exit_ts, timeframeS);
    if (exitIdx === null) notes.push("desfecho do sinal fora dos candles carregados");
    else markers.push({ time: times[exitIdx] as Time, position: "aboveBar", shape: "circle", color: chartColor(RESULT_COLOR_VAR[signal.result] ?? "--color-fg-muted"), text: signal.r_multiple !== null ? `${Number(signal.r_multiple).toFixed(2)}R` : signal.result });
  }

  return { markers, notes, series };
}

/**
 * The confluence screen's own candlestick chart (design §2-§3): candles at
 * the caller's chosen timeframe, real `spot/1` entries/exits always marked in
 * time (never on the price axis), and -- only for the selected signal --
 * its reference/stop/target and direction/exit. Every element that cannot be
 * placed on the loaded candles is named in `notes`, never approximated.
 */
export function ConfluenceChart({ candles, timeframeSeconds, positions, selectedSignal, onBarClick, onReady, onRangeChange }: ConfluenceChartProps) {
  const [container, setContainer] = useState<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const [failed, setFailed] = useState(false);
  const [notes, setNotes] = useState<string[]>([]);
  const theme = useThemeAttribute();
  const candleData = toChartData(candles);
  const times = candleData.map((c) => c.time as UTCTimestamp);

  useEffect(() => {
    if (!container || candleData.length === 0) return undefined;
    let disposed = false;
    let chart: IChartApi | undefined;
    try {
      chart = createChart(container, {
        height: CHART_HEIGHT,
        timeScale: { timeVisible: true, secondsVisible: false, tickMarkFormatter: brasiliaTickMarkFormatter },
        localization: { timeFormatter: brasiliaCrosshairLabel },
        ...layoutOptions(),
      });
      const series = chart.addSeries(CandlestickSeries, candleSeriesOptions());
      series.setData(candleData);
      const markersApi = createSeriesMarkers(series, []);
      seriesRef.current = series;
      markersRef.current = markersApi;
    } catch (error) {
      logger.warn("confluence_chart_init_failed", { error: String(error) });
      chart?.remove();
      chartRef.current = null;
      seriesRef.current = null;
      markersRef.current = null;
      // eslint-disable-next-line react-hooks/set-state-in-effect -- reflects the outcome of creating the external chart instance, not a value derived from props/state
      setFailed(true);
      onReady?.(null);
      return undefined;
    }
    chartRef.current = chart;
    setFailed(false);
    onReady?.(chart);
    const resize = () => {
      if (disposed) return;
      chart?.applyOptions({ width: container.clientWidth });
      onRangeChange?.();
    };
    const clickHandler = (param: MouseEventParams<Time>) => {
      if (param.time === undefined || onBarClick === undefined) return;
      onBarClick(new Date((param.time as number) * 1000).toISOString());
    };
    resize();
    chart.subscribeClick(clickHandler);
    chart.timeScale().subscribeVisibleTimeRangeChange(() => onRangeChange?.());
    window.addEventListener("resize", resize);
    return () => {
      disposed = true;
      window.removeEventListener("resize", resize);
      chart?.unsubscribeClick(clickHandler);
      chart?.remove();
      chartRef.current = null;
      seriesRef.current = null;
      markersRef.current = null;
      onReady?.(null);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- (re)created once per mount/candle-set change; theme/overlay updates are the effects below
  }, [container, candleData.length]);

  useEffect(() => {
    const chart = chartRef.current;
    const series = seriesRef.current;
    if (!chart || !series) return;
    chart.applyOptions(layoutOptions());
    series.applyOptions(candleSeriesOptions());
  }, [theme]);

  // Astra's review of T4.82 (must-fix 6): the creation effect above only
  // reinitializes on `candleData.length` -- a timeframe switch that happens
  // to return the same bar count (e.g. 500 either way) would otherwise leave
  // the OLD timeframe's candles on screen while the panel/overlays already
  // moved on to the new one. This keeps the series' own data in sync with
  // `candles` on every render, independent of whether the length changed.
  useEffect(() => {
    seriesRef.current?.setData(candleData);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `candleData` is derived fresh from `candles` every render; keying on `candles` itself avoids re-running this on every unrelated render
  }, [candles]);

  // The overlay itself: real markers always, selected-signal geometry only
  // when present. Rebuilt from scratch on every relevant prop change --
  // `LineSeries` instances added by the previous pass are removed first so
  // a de-selected signal's lines do not linger.
  const addedSeriesRef = useRef<ISeriesApi<"Line">[]>([]);
  useEffect(() => {
    const chart = chartRef.current;
    const markersApi = markersRef.current;
    if (!chart || !markersApi || times.length === 0) return;
    for (const series of addedSeriesRef.current) chart.removeSeries(series);
    addedSeriesRef.current = [];

    const real = buildRealMarkers(times, positions, timeframeSeconds);
    let signalMarkers: SeriesMarker<Time>[] = [];
    let signalNotes: string[] = [];
    if (selectedSignal !== null) {
      const overlay = buildSignalOverlay(chart, times, selectedSignal, timeframeSeconds);
      signalMarkers = overlay.markers;
      signalNotes = overlay.notes;
      addedSeriesRef.current = overlay.series;
    }
    markersApi.setMarkers([...real.markers, ...signalMarkers]);
    setNotes([...real.notes, ...signalNotes]);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `times`/`candleData` are derived fresh every render from `candles`; re-keying on `candles` itself avoids re-running on every render
  }, [candles, positions, selectedSignal, timeframeSeconds]);

  if (candles.length === 0) {
    return <p className="flex h-[320px] items-center justify-center text-sm text-fg-muted">Sem candles neste período para este mercado.</p>;
  }
  if (failed) {
    return (
      <div className="flex h-[320px] flex-col items-center justify-center gap-1 text-center text-sm">
        <p className="text-fg">Gráfico indisponível.</p>
        <p className="text-fg-muted">Os dados chegaram, mas o gráfico não pôde ser desenhado. Recarregue a página.</p>
      </div>
    );
  }
  return (
    <div>
      <div ref={setContainer} className="w-full" />
      {notes.length > 0 && (
        <ul className="mt-1 flex flex-col gap-0.5 text-[11px] text-fg-subtle">
          {notes.map((note) => (
            <li key={note}>· {note}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
