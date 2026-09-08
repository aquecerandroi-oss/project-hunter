"use client";

import { createChart, LineSeries, type IChartApi, type ISeriesApi, type LineData, type Time, type TickMarkType, type UTCTimestamp } from "lightweight-charts";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { LabVerdictBadge } from "@/components/lab/lab-verdict-badge";
import { rToUsdt, type MoneyRuler } from "@/components/lab/lab-money";
import { verdictLineColorVar, type LabCurveSeriesInput } from "@/components/lab/lab-scoreboard";
import { chartColor } from "@/lib/charts/css-var";
import { alignToUnionTimes, sanitizeLinePoints } from "@/lib/charts/series-data";
import { logger } from "@/lib/logger";
import { formatBrasiliaTick, formatBrasiliaWithUtcTooltip } from "@/lib/time";

export interface LabCurveChartProps {
  series: LabCurveSeriesInput[];
  ruler: MoneyRuler;
}

const CHART_HEIGHT = 200;
/** `lightweight-charts`' own `LineStyle.Dashed` (2) / `LineStyle.Solid` (0) --
 * a literal, not the imported enum, so the module under test never breaks a
 * mock that only stubs `LineSeries`/`createChart` (brief T3.24b addendum
 * A3). */
const DASHED_LINE_STYLE = 2;
const SOLID_LINE_STYLE = 0;
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

function toUnix(iso: string): UTCTimestamp {
  return Math.floor(new Date(iso).getTime() / 1000) as UTCTimestamp;
}

/** `cum_r` converted through the ruler for the USDT view, or kept as a plain R number for the toggle (brief item 4: "cumulative simulated result in USDT through the ruler; toggle to R"). Sanitized (T3.31): non-finite values dropped, sorted and deduped by time before this ever reaches `lightweight-charts`. */
function toSeriesData(entry: LabCurveSeriesInput, currency: ChartCurrency, ruler: MoneyRuler): LineData<Time>[] {
  const raw = entry.points.map((p) => ({ time: toUnix(p.ts), value: currency === "usdt" ? rToUsdt(p.cum_r, ruler) : Number(p.cum_r) }));
  return sanitizeLinePoints(raw) as LineData<Time>[];
}

function chartLayoutOptions() {
  return {
    layout: { background: { color: "transparent" as const }, textColor: chartColor("--color-fg-muted") },
    grid: { vertLines: { color: chartColor("--color-border") }, horzLines: { color: chartColor("--color-border") } },
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

/** Unique per (version, cohort) -- `attachSeries`' own map key, so a replay overlay never collides with the prospective line of the same version (brief T3.24b addendum A3). */
function seriesKey(entry: LabCurveSeriesInput): string {
  return `${entry.versionId}:${entry.cohort ?? "prospective"}`;
}

/**
 * One line per (version, cohort) with resolved points, coloured by its own
 * verdict (brief item 4: "same colours as the cards") -- a version with no
 * resolved outcome yet draws no line at all, never a flat fabricated one.
 * `cohort: "replay"` draws dashed, alongside the (solid) prospective line for
 * the same version (addendum A3) -- never conflated into one line.
 */
function attachSeries(chart: IChartApi, series: LabCurveSeriesInput[], currency: ChartCurrency, ruler: MoneyRuler): Map<string, ISeriesApi<"Line">> {
  const drawable = series.filter((entry) => entry.points.length > 0);
  // T3.31 root cause: `lightweight-charts` shares one time scale across every
  // series on this chart -- each version's line only has points for the
  // timestamps that version actually signalled, so two lines here almost
  // never share the exact same times. Without this alignment, a series asked
  // to resolve its own bar at a time only a sibling series has crashes with
  // "Error: Value is null" (`.claude/state/notes-T3.31.md`).
  const aligned = alignToUnionTimes(drawable.map((entry) => toSeriesData(entry, currency, ruler)));
  const map = new Map<string, ISeriesApi<"Line">>();
  drawable.forEach((entry, index) => {
    const line = chart.addSeries(LineSeries, {
      color: chartColor(verdictLineColorVar(entry.verdict)),
      lineWidth: 2,
      lineStyle: entry.cohort === "replay" ? DASHED_LINE_STYLE : SOLID_LINE_STYLE,
    });
    line.setData(aligned[index] ?? []);
    map.set(seriesKey(entry), line);
  });
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
    // T3.31: a stable, effect-local flag (not the mutable `chartRef`) so a
    // callback that outlives this effect's own lifetime (e.g. a `resize`
    // event already queued the instant cleanup runs) can never act on a
    // chart this same effect has already torn down -- idempotent under
    // React strict mode's mount/cleanup/mount cycle.
    let disposed = false;
    let chart: IChartApi | undefined;
    try {
      chart = createChart(container, {
        height: CHART_HEIGHT,
        timeScale: { timeVisible: true, secondsVisible: false, tickMarkFormatter: brasiliaTickMarkFormatter },
        localization: { timeFormatter: brasiliaCrosshairLabel },
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
      seriesRefs.current.get(seriesKey(entry))?.applyOptions({ color: chartColor(verdictLineColorVar(entry.verdict)) });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `series` is read fresh, not a reactive dependency of a theme-only effect
  }, [theme]);

  useEffect(() => {
    const drawableNow = series.filter((entry) => entry.points.length > 0);
    // Same union-of-times alignment as the creation effect (T3.31) -- a
    // currency toggle or a refetch calls `setData` again on every series,
    // and would reopen the exact same gap if only re-sanitized in isolation.
    const aligned = alignToUnionTimes(drawableNow.map((entry) => toSeriesData(entry, currency, ruler)));
    drawableNow.forEach((entry, index) => {
      seriesRefs.current.get(seriesKey(entry))?.setData(aligned[index] ?? []);
    });
  }, [series, currency, ruler]);

  if (drawable.length === 0) {
    return <p className="flex h-[200px] items-center justify-center text-sm text-fg-muted">Nenhum resultado resolvido ainda para desenhar a curva.</p>;
  }

  if (failed) {
    return (
      <div className="flex h-[200px] flex-col items-center justify-center gap-1 text-center text-sm">
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
          <li key={seriesKey(entry)} className="flex items-center gap-1.5 text-xs text-fg-muted">
            <span
              className={entry.cohort === "replay" ? "inline-block h-0 w-3 border-t-2 border-dashed" : "inline-block h-2 w-2 rounded-full"}
              style={entry.cohort === "replay" ? { borderColor: chartColor(verdictLineColorVar(entry.verdict)) } : { backgroundColor: chartColor(verdictLineColorVar(entry.verdict)) }}
            />
            <span className="font-mono text-fg">{entry.label}</span>
            {entry.cohort === "replay" ? (
              <span className="text-fg-subtle">replay — não conta para o veredito</span>
            ) : (
              entry.cohort === "prospective" && <span className="text-fg-subtle">prospectiva</span>
            )}
            <LabVerdictBadge verdict={entry.verdict} />
            {entry.truncated && <span className="text-fg-subtle">(primeiros 2.000 pontos)</span>}
            {entry.failed && <span className="text-warning">(curva indisponível: falha ao carregar)</span>}
            {!entry.failed && entry.points.length === 0 && <span className="text-fg-subtle">(sem resultado resolvido ainda)</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}
