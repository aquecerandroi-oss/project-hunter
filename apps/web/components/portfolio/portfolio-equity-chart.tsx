"use client";

import {
  createChart,
  createSeriesMarkers,
  LineSeries,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type LineData,
  type SeriesMarker,
  type TickMarkType,
  type Time,
  type UTCTimestamp,
  type WhitespaceData,
} from "lightweight-charts";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { PortfolioAsOf } from "@/components/portfolio/portfolio-as-of";
import { brlUnavailableLabel } from "@/components/portfolio/portfolio-format";
import type { EquityCurvePoint } from "@/lib/api/portfolio-types";
import { chartColor } from "@/lib/charts/css-var";
import { sanitizeLinePoints } from "@/lib/charts/series-data";
import { logger } from "@/lib/logger";
import { formatBrasiliaTick, formatBrasiliaWithUtcTooltip } from "@/lib/time";

export interface PortfolioEquityChartProps {
  points: EquityCurvePoint[];
  asOf: string;
}

const CHART_HEIGHT = 280;
type ChartCurrency = "usdt" | "brl";
type ThemeName = "dark" | "light";

function readTheme(): ThemeName {
  if (typeof document === "undefined") return "dark";
  return document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
}

/** Mirrors `components/markets/candles-chart.tsx`'s own observer -- `ThemeToggle` dispatches no event, so a `MutationObserver` on `data-theme` is the only way to react to a theme flip in an already-open tab. */
function useThemeAttribute(): ThemeName {
  const [theme, setTheme] = useState<ThemeName>(readTheme);
  useEffect(() => {
    const observer = new MutationObserver(() => setTheme(readTheme()));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, []);
  return theme;
}

function toUnix(iso: string): UTCTimestamp {
  return Math.floor(new Date(iso).getTime() / 1000) as UTCTimestamp;
}

/** Creates the line series, its initial data and its markers plugin -- split out of the creation effect purely to stay under the statement-count lint budget. */
function attachSeries(
  chart: IChartApi,
  points: EquityCurvePoint[],
  currency: ChartCurrency,
): { series: ISeriesApi<"Line">; markers: ISeriesMarkersPluginApi<Time> } {
  const series = chart.addSeries(LineSeries, { color: chartColor("--color-info"), lineWidth: 2 });
  series.setData(toSeriesData(points, currency));
  return { series, markers: createSeriesMarkers(series, []) };
}

/** Mirrors `candles-chart.tsx`'s own `layoutOptions()` -- extracted so the creation effect stays under the statement-count lint budget. */
function chartLayoutOptions() {
  return {
    layout: { background: { color: "transparent" as const }, textColor: chartColor("--color-fg-muted") },
    grid: {
      vertLines: { color: chartColor("--color-border") },
      horzLines: { color: chartColor("--color-border") },
    },
  };
}

/**
 * Brief T3.22 (2026-09-08): chart axis ticks and the crosshair label read in
 * Brasília, never the viewer's browser timezone -- `time` is this chart's
 * own `UTCTimestamp` (whole seconds since the UTC epoch), the same value
 * `toUnix` produces below, so the cast to `number` is safe.
 */
function brasiliaTickMarkFormatter(time: Time, tickMarkType: TickMarkType): string {
  return formatBrasiliaTick(time as number, tickMarkType);
}

/** The crosshair label shows both halves (brief item 6: "tooltip shows Brasília and UTC"). */
function brasiliaCrosshairLabel(time: Time): string {
  return formatBrasiliaWithUtcTooltip(new Date((time as number) * 1000).toISOString());
}

/**
 * USDT is always present (`EquityCurvePointOut.equity` is never null); BRL is
 * either the point's own reading or a gap (`WhitespaceData`, no `value`) --
 * never today's rate stretched back onto a point that never had one (M3
 * joint decision, item 1). A gap still occupies its timestamp on the series,
 * which is what lets a marker attach to it below.
 */
function toSeriesData(points: EquityCurvePoint[], currency: ChartCurrency): (LineData<Time> | WhitespaceData<Time>)[] {
  const raw = points.map((p) => {
    const time = toUnix(p.ts);
    if (currency === "usdt") return { time, value: Number(p.equity) };
    if (p.brl_equity === null) return { time };
    return { time, value: Number(p.brl_equity) };
  });
  // T3.31: non-finite values dropped, sorted and deduped by time before this
  // ever reaches `lightweight-charts` (`.claude/state/notes-T3.31.md`).
  return sanitizeLinePoints(raw);
}

function missingBrlPoints(points: EquityCurvePoint[]): EquityCurvePoint[] {
  return points.filter((p) => p.brl_equity === null);
}

/** A shared reason across every gap, when there is one -- lets the caption name it instead of listing N different reasons. */
function commonMissingReason(missing: EquityCurvePoint[]): string | null {
  if (missing.length === 0) return null;
  const reasons = new Set(missing.map((p) => p.brl_unavailable_reason ?? "sem motivo informado"));
  if (reasons.size !== 1) return null;
  const [only] = reasons;
  return only ?? null;
}

/**
 * The equity curve (brief item 5): USDT always, BRL via a toggle (not a
 * second axis -- simpler to read at a glance, and `lightweight-charts`' two
 * price scales would still need this exact same gap/marker handling for the
 * BRL side). Points without a BRL reading render as a genuine gap in the
 * line, marked with a warning dot -- never interpolated or backfilled with
 * today's rate.
 */
export function PortfolioEquityChart({ points, asOf }: PortfolioEquityChartProps) {
  const [container, setContainer] = useState<HTMLDivElement | null>(null);
  const [currency, setCurrency] = useState<ChartCurrency>("usdt");
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const [failed, setFailed] = useState(false);
  const theme = useThemeAttribute();

  const missing = missingBrlPoints(points);
  const commonReason = commonMissingReason(missing);

  function clearRefs(): void {
    chartRef.current = null;
    seriesRef.current = null;
    markersRef.current = null;
  }

  useEffect(() => {
    if (!container) return undefined;

    // T3.31: an effect-local flag (not the mutable `chartRef`) so a callback
    // that outlives this effect (e.g. a `resize` event already queued the
    // instant cleanup runs) can never act on an already-torn-down chart --
    // idempotent under React strict mode's mount/cleanup/mount cycle.
    let disposed = false;
    let chart: IChartApi | undefined;
    try {
      chart = createChart(container, {
        height: CHART_HEIGHT,
        timeScale: { timeVisible: true, secondsVisible: false, tickMarkFormatter: brasiliaTickMarkFormatter },
        localization: { timeFormatter: brasiliaCrosshairLabel },
        ...chartLayoutOptions(),
      });
      // The initial paint happens inside `attachSeries` (not only in the
      // `[points, currency]` effect below): `container` starts `null` (the
      // ref callback fires only after the first commit), so this effect's
      // *own* first real run already lands on a later render than the one
      // that set `points` -- the update effect would not fire again on its
      // own since neither `points` nor `currency` changed between those two
      // renders (mirrors `candles-chart.tsx`'s own immediate `setData` call
      // right after creation, for the identical reason).
      const { series, markers } = attachSeries(chart, points, currency);
      seriesRef.current = series;
      markersRef.current = markers;
    } catch (error) {
      logger.warn("portfolio_equity_chart_init_failed", { error: String(error) });
      chart?.remove();
      clearRefs();
      // eslint-disable-next-line react-hooks/set-state-in-effect -- reflects the real outcome of creating the external chart instance, not a value derived from props/state
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
    // eslint-disable-next-line react-hooks/exhaustive-deps -- (re)created only when the container mounts/unmounts; `points`/`currency` updates after creation are handled by the effect below, which reads fresh values on its own deps
  }, [container]);

  useEffect(() => {
    const chart = chartRef.current;
    const series = seriesRef.current;
    if (!chart || !series) return;
    chart.applyOptions(chartLayoutOptions());
    series.applyOptions({ color: chartColor("--color-info") });
  }, [theme]);

  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;
    series.setData(toSeriesData(points, currency));

    const markerColor = chartColor("--color-warning");
    const markers: SeriesMarker<Time>[] =
      currency === "brl"
        ? missing.map((p) => ({
            time: toUnix(p.ts),
            position: "aboveBar",
            shape: "circle",
            color: markerColor,
            text: "sem BRL",
          }))
        : [];
    markersRef.current?.setMarkers(markers);
    // `missing` is derived from `points` every render (not memoized) -- cheap enough for a <= 200-point page, and avoids a second dependency array to keep in sync.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [points, currency]);

  if (points.length === 0) {
    return <p className="flex h-[280px] items-center justify-center text-sm text-fg-muted">Sem pontos na curva de patrimônio ainda.</p>;
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
        <h3 className="text-sm font-semibold text-fg">Curva de patrimônio</h3>
        <div className="flex gap-1">
          <Button type="button" size="sm" variant={currency === "usdt" ? "default" : "outline"} onClick={() => setCurrency("usdt")}>
            USDT
          </Button>
          <Button type="button" size="sm" variant={currency === "brl" ? "default" : "outline"} onClick={() => setCurrency("brl")}>
            BRL
          </Button>
        </div>
      </div>
      <div ref={setContainer} className="mt-3 w-full" />
      <p className="mt-2 text-xs text-fg-muted">
        {points.length} pontos · consultado em <PortfolioAsOf iso={asOf} />
        {currency === "brl" && missing.length > 0 && (
          <>
            {" "}
            · {missing.length} sem leitura BRL{commonReason ? ` (${brlUnavailableLabel(commonReason)})` : ""}
          </>
        )}
      </p>
    </div>
  );
}
