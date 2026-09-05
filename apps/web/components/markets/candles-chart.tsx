"use client";

import { CandlestickSeries, createChart, type IChartApi, type ISeriesApi, type UTCTimestamp } from "lightweight-charts";
import { useEffect, useRef, useState } from "react";

import type { Candle } from "@/lib/api/types";
import { logger } from "@/lib/logger";

export interface CandlesChartProps {
  candles: Candle[];
}

const CHART_HEIGHT = 360;

type ThemeName = "dark" | "light";

function readTheme(): ThemeName {
  if (typeof document === "undefined") return "dark";
  return document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
}

/**
 * `ThemeToggle` (components/layout/theme-toggle.tsx) flips theme by calling
 * `document.documentElement.setAttribute("data-theme", ...)` directly -- it
 * dispatches no event of its own. A `MutationObserver` on that one attribute
 * is the only way anything outside the toggle can learn the theme changed in
 * an already-open tab (T1.5 review F5): without it, this component's colors
 * (read once at chart-creation time below) stay frozen on the theme that was
 * active when the chart was first created.
 */
function useThemeAttribute(): ThemeName {
  const [theme, setTheme] = useState<ThemeName>(readTheme);
  useEffect(() => {
    const observer = new MutationObserver(() => setTheme(readTheme()));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, []);
  return theme;
}

/** Live value of a docs/DESIGN.md token (`app/globals.css`'s `@theme`); never a hardcoded hex fallback (docs/DESIGN.md §1: "nunca usar hex solto"). */
function cssVar(name: string): string {
  if (typeof window === "undefined") return "";
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function toChartData(candles: Candle[]) {
  return candles.map((candle) => ({
    time: Math.floor(new Date(candle.open_time).getTime() / 1000) as UTCTimestamp,
    open: Number(candle.open),
    high: Number(candle.high),
    low: Number(candle.low),
    close: Number(candle.close),
  }));
}

function layoutOptions() {
  return {
    layout: { background: { color: "transparent" as const }, textColor: cssVar("--color-fg-muted") },
    grid: {
      vertLines: { color: cssVar("--color-border") },
      horzLines: { color: cssVar("--color-border") },
    },
  };
}

function seriesOptions() {
  const gold = cssVar("--color-gold");
  const red = cssVar("--color-red");
  return {
    upColor: gold,
    borderUpColor: gold,
    wickUpColor: gold,
    downColor: red,
    borderDownColor: red,
    wickDownColor: red,
  };
}

/**
 * 1m candles, last 500 (docs/plans/M1.md T1.5), TradingView-style density
 * (docs/DESIGN.md): gold up, red down. The only place in the app that
 * converts a `Decimal` string to `number` -- the charting library only
 * accepts floats, and nothing downstream reads these values back as money
 * (CLAUDE.md's Decimal rule applies to stored/transmitted values, not a
 * canvas pixel position).
 */
export function CandlesChart({ candles }: CandlesChartProps) {
  // A callback ref surfaced as state (not a plain `useRef`) so the creation
  // effect below can depend on "is the container actually mounted". With
  // `candles.length === 0` rendering the empty-state paragraph instead of
  // this component's `<div>`, a plain ref stays null forever once the
  // component first mounts with zero candles -- a `[]`-deps effect would
  // never run again once real candles arrive on a later refresh (T1.5
  // review F1).
  const [container, setContainer] = useState<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const [failed, setFailed] = useState(false);
  const theme = useThemeAttribute();

  useEffect(() => {
    if (!container) return undefined;

    let chart: IChartApi | undefined;
    try {
      chart = createChart(container, {
        height: CHART_HEIGHT,
        timeScale: { timeVisible: true, secondsVisible: false },
        ...layoutOptions(),
      });
      seriesRef.current = chart.addSeries(CandlestickSeries, seriesOptions());
      seriesRef.current.setData(toChartData(candles));
    } catch (error) {
      logger.warn("candles_chart_init_failed", { error: String(error) });
      chart?.remove();
      chartRef.current = null;
      seriesRef.current = null;
      // eslint-disable-next-line react-hooks/set-state-in-effect -- reflects the real outcome of creating the external chart instance (lightweight-charts), not a value derived from props/state
      setFailed(true);
      return undefined;
    }

    chartRef.current = chart;
    setFailed(false);
    const resize = () => chart?.applyOptions({ width: container.clientWidth });
    resize();
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      chart?.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- (re)created only when the container mounts/unmounts; candle updates and theme re-coloring are the two effects below
  }, [container]);

  // Re-applies tokens onto the existing chart/series (no teardown, so zoom
  // and scroll position survive) whenever `ThemeToggle` flips `data-theme`
  // (T1.5 review F5).
  useEffect(() => {
    const chart = chartRef.current;
    const series = seriesRef.current;
    if (!chart || !series) return;
    chart.applyOptions(layoutOptions());
    series.applyOptions(seriesOptions());
  }, [theme]);

  useEffect(() => {
    seriesRef.current?.setData(toChartData(candles));
  }, [candles]);

  if (candles.length === 0) {
    return (
      <p className="flex h-[360px] items-center justify-center text-sm text-fg-muted">
        Sem candles ainda para este mercado.
      </p>
    );
  }

  // Distinct from the empty state above (T1.5 review F4): candles arrived,
  // but the charting library itself failed to initialize -- an empty div
  // here would be indistinguishable from "still loading".
  if (failed) {
    return (
      <div className="flex h-[360px] flex-col items-center justify-center gap-1 text-center text-sm">
        <p className="text-fg">Gráfico indisponível.</p>
        <p className="text-fg-muted">Os dados de candles chegaram, mas o gráfico não pôde ser desenhado. Recarregue a página.</p>
      </div>
    );
  }

  return <div ref={setContainer} className="w-full" />;
}
