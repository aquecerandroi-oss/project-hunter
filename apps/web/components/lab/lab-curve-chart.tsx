"use client";

import { createChart, LineSeries, type IChartApi, type ISeriesApi, type LineData, type Time, type UTCTimestamp } from "lightweight-charts";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { LabVerdictBadge } from "@/components/lab/lab-verdict-badge";
import { rToUsdt, type MoneyRuler } from "@/components/lab/lab-money";
import { verdictLineColorVar, type LabCurveSeriesInput } from "@/components/lab/lab-scoreboard";
import { logger } from "@/lib/logger";

export interface LabCurveChartProps {
  series: LabCurveSeriesInput[];
  ruler: MoneyRuler;
}

const CHART_HEIGHT = 280;
type ChartCurrency = "usdt" | "r";
type ThemeName = "dark" | "light";

function readTheme(): ThemeName {
  if (typeof document === "undefined") return "dark";
  return document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
}

/** Mirrors `portfolio-equity-chart.tsx`'s own observer -- the theme toggle dispatches no event. */
function useThemeAttribute(): ThemeName {
  const [theme, setTheme] = useState<ThemeName>(readTheme);
  useEffect(() => {
    const observer = new MutationObserver(() => setTheme(readTheme()));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, []);
  return theme;
}

function cssVar(name: string): string {
  if (typeof window === "undefined") return "";
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function toUnix(iso: string): UTCTimestamp {
  return Math.floor(new Date(iso).getTime() / 1000) as UTCTimestamp;
}

/** `cum_r` converted through the ruler for the USDT view, or kept as a plain R number for the toggle (brief item 4: "cumulative simulated result in USDT through the ruler; toggle to R"). */
function toSeriesData(entry: LabCurveSeriesInput, currency: ChartCurrency, ruler: MoneyRuler): LineData<Time>[] {
  return entry.points.map((p) => ({ time: toUnix(p.ts), value: currency === "usdt" ? rToUsdt(p.cum_r, ruler) : Number(p.cum_r) }));
}

function chartLayoutOptions() {
  return {
    layout: { background: { color: "transparent" as const }, textColor: cssVar("--color-fg-muted") },
    grid: { vertLines: { color: cssVar("--color-border") }, horzLines: { color: cssVar("--color-border") } },
  };
}

/** One line per version with resolved points, coloured by its own verdict (brief item 4: "same colours as the cards") -- a version with no resolved outcome yet draws no line at all, never a flat fabricated one. */
function attachSeries(chart: IChartApi, series: LabCurveSeriesInput[], currency: ChartCurrency, ruler: MoneyRuler): Map<string, ISeriesApi<"Line">> {
  const map = new Map<string, ISeriesApi<"Line">>();
  for (const entry of series) {
    if (entry.points.length === 0) continue;
    const line = chart.addSeries(LineSeries, { color: cssVar(verdictLineColorVar(entry.verdict)), lineWidth: 2 });
    line.setData(toSeriesData(entry, currency, ruler));
    map.set(entry.versionId, line);
  }
  return map;
}

/**
 * The Placar's curve (brief T3.18 item 4): one line per version, cumulative
 * simulated result via the T3.17 ruler by default, toggled to raw R. Same
 * `lightweight-charts` approach as `components/portfolio/portfolio-equity-chart.tsx`
 * -- no new charting library. Hover shows date/value through the library's
 * own crosshair + axis labels (the equity chart relies on the same built-in
 * behaviour rather than a hand-rolled tooltip).
 */
export function LabCurveChart({ series, ruler }: LabCurveChartProps) {
  const [container, setContainer] = useState<HTMLDivElement | null>(null);
  const [currency, setCurrency] = useState<ChartCurrency>("usdt");
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRefs = useRef<Map<string, ISeriesApi<"Line">>>(new Map());
  const [failed, setFailed] = useState(false);
  const theme = useThemeAttribute();

  const drawable = series.filter((entry) => entry.points.length > 0);

  useEffect(() => {
    if (!container) return undefined;
    let chart: IChartApi | undefined;
    try {
      chart = createChart(container, {
        height: CHART_HEIGHT,
        timeScale: { timeVisible: true, secondsVisible: false },
        ...chartLayoutOptions(),
      });
      seriesRefs.current = attachSeries(chart, series, currency, ruler);
    } catch (error) {
      logger.warn("lab_curve_chart_init_failed", { error: String(error) });
      chart?.remove();
      seriesRefs.current = new Map();
      chartRef.current = null;
      // eslint-disable-next-line react-hooks/set-state-in-effect -- reflects the real outcome of creating the external chart instance
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
      seriesRefs.current = new Map();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- created once per mount, same rationale as `portfolio-equity-chart.tsx`; `series`/`currency`/`ruler` updates are handled by the effect below
  }, [container]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    chart.applyOptions(chartLayoutOptions());
    for (const entry of series) {
      seriesRefs.current.get(entry.versionId)?.applyOptions({ color: cssVar(verdictLineColorVar(entry.verdict)) });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `series` is read fresh, not a reactive dependency of a theme-only effect
  }, [theme]);

  useEffect(() => {
    for (const entry of series) {
      seriesRefs.current.get(entry.versionId)?.setData(toSeriesData(entry, currency, ruler));
    }
  }, [series, currency, ruler]);

  if (drawable.length === 0) {
    return <p className="flex h-[280px] items-center justify-center text-sm text-fg-muted">Nenhum resultado resolvido ainda para desenhar a curva.</p>;
  }

  if (failed) {
    return (
      <div className="flex h-[280px] flex-col items-center justify-center gap-1 text-center text-sm">
        <p className="text-fg">Gráfico indisponível.</p>
        <p className="text-fg-muted">Os pontos da curva chegaram, mas o gráfico não pôde ser desenhado. Recarregue a página.</p>
      </div>
    );
  }

  return (
    <div className="rounded-md border border-border p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-fg">Curva de resultado simulado</h3>
        <div className="flex gap-1">
          <Button type="button" size="sm" variant={currency === "usdt" ? "default" : "outline"} onClick={() => setCurrency("usdt")}>
            USDT
          </Button>
          <Button type="button" size="sm" variant={currency === "r" ? "default" : "outline"} onClick={() => setCurrency("r")}>
            R
          </Button>
        </div>
      </div>
      <div ref={setContainer} className="mt-3 w-full" />
      <ul data-testid="lab-curve-legend" className="mt-3 flex flex-wrap gap-3">
        {series.map((entry) => (
          <li key={entry.versionId} className="flex items-center gap-1.5 text-xs text-fg-muted">
            <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: cssVar(verdictLineColorVar(entry.verdict)) }} />
            <span className="font-mono text-fg">{entry.label}</span>
            <LabVerdictBadge verdict={entry.verdict} />
            {entry.truncated && <span className="text-fg-subtle">(capado em 2.000 pontos)</span>}
            {entry.failed && <span className="text-warning">(curva indisponível: falha ao carregar)</span>}
            {!entry.failed && entry.points.length === 0 && <span className="text-fg-subtle">(sem resultado resolvido ainda)</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}
