/**
 * The bonding-curve mcap series (detail page) -- same no-library, calm SVG
 * convention as `components/lab/lab-daily-goal-sparkline.tsx`
 * (docs/DESIGN.md §2 "movimento calmo"), extended for a **time** x-axis
 * (points are not evenly spaced -- a real gap between snapshots must read as
 * a longer segment, never as if the feed sampled continuously through it).
 * `stroke="currentColor"` makes it theme-aware: it inherits whatever
 * `text-*` class wraps it, so it renders correctly in dark and light
 * without its own branch.
 *
 * `mcap_sol` can be `null` for a given snapshot (generated column, `NULLIF`
 * when `virtual_token_reserves = 0` -- contract §2). Those points are
 * dropped before drawing rather than treated as `0`, and their count is
 * reported honestly in the caption instead of silently vanishing.
 *
 * T4.2d: `marks` are the completion signals (`meme-graduation-signals.ts`)
 * drawn as vertical lines at their instants -- only inside the drawn span;
 * a signal outside it (a `gd` before the first snapshot) is listed beside
 * the chart, never squeezed onto its edge.
 *
 * T4.10b: `features` (the per-minute series) draws the trend lines the
 * backend computed -- support through the last two lows projected to now,
 * the previous window's 15-minute high, the breakout mark
 * (`meme-lines.ts` + `meme-curve-lines.tsx`) -- on the same time/value scale
 * as the curve, and says "linha ainda não traçável: <motivo>" or "linha: sem
 * leitura" when there is nothing to draw.
 */
import type { MemeFeaturePoint, MemeSnapshotPoint } from "@/lib/api/meme-types";

import { CurveLinesCaption, CurveLinesLayer } from "./meme-curve-lines";
import type { SignalMark } from "./meme-graduation-signals";
import { lineOverlay } from "./meme-lines";

export interface CurvePoint {
  x: number;
  y: number;
}

export interface CurveChartGeometry {
  linePoints: string;
  min: number;
  max: number;
  minX: number;
  maxX: number;
}

const WIDTH = 320;
const HEIGHT = 64;

/** Pure scale math (unit-tested on its own, `tests/meme-curve-chart.test.ts`): maps chronological `(timestamp, value)` points onto a `WIDTH`x`HEIGHT` box by real elapsed time, not by index -- a gap between two snapshots stretches proportionally, it never looks like continuous sampling. */
export function curveChartGeometry(points: CurvePoint[]): CurveChartGeometry | null {
  if (points.length < 2) return null;
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const spanX = maxX - minX || 1;
  const spanY = maxY - minY || 1;
  const scaleX = (x: number): number => ((x - minX) / spanX) * WIDTH;
  const scaleY = (y: number): number => (maxY === minY ? HEIGHT / 2 : HEIGHT - ((y - minY) / spanY) * HEIGHT);
  const linePoints = points.map((p) => `${scaleX(p.x)},${scaleY(p.y)}`).join(" ");
  return { linePoints, min: minY, max: maxY, minX, maxX };
}

/** The drawn x of an instant, by the same time scale as the line; `null` outside the drawn span. */
export function markX(geometry: Pick<CurveChartGeometry, "minX" | "maxX">, x: number): number | null {
  if (x < geometry.minX || x > geometry.maxX) return null;
  const spanX = geometry.maxX - geometry.minX || 1;
  return ((x - geometry.minX) / spanX) * WIDTH;
}

/** The drawn y of a value, by the same value scale as the line (a value outside the series' range lands outside the box and is clipped, never rescales the curve). */
export function markY(geometry: Pick<CurveChartGeometry, "min" | "max">, y: number): number {
  if (geometry.max === geometry.min) return HEIGHT / 2;
  return HEIGHT - ((y - geometry.min) / (geometry.max - geometry.min)) * HEIGHT;
}

export interface MemeCurveChartProps {
  snapshots: MemeSnapshotPoint[];
  marks?: SignalMark[];
  /** T4.10b: the feature series (any order); the lines come from its latest two minutes. Omitted = curve only, no line caption. */
  features?: MemeFeaturePoint[];
}

/** Newest-last order expected (chronological, left to right) -- callers pass `[...snapshots].reverse()` when the API returned newest-first (it does, `GET .../tokens/{mint}`). */
export function MemeCurveChart({ snapshots, marks = [], features }: MemeCurveChartProps) {
  const withValue = snapshots.filter((s): s is MemeSnapshotPoint & { mcap_sol: string } => s.mcap_sol !== null);
  const omitted = snapshots.length - withValue.length;
  const points: CurvePoint[] = withValue.map((s) => ({ x: new Date(s.observed_at).getTime(), y: Number(s.mcap_sol) }));
  const geometry = curveChartGeometry(points);
  const overlay = features ? lineOverlay(features, geometry) : null;

  if (!geometry) {
    return (
      <div>
        <p className="text-xs text-fg-muted">Sem histórico suficiente para o gráfico de mcap.</p>
        {overlay && <CurveLinesCaption overlay={overlay} />}
      </div>
    );
  }

  const drawn = marks.map((mark) => ({ ...mark, x: markX(geometry, mark.x) })).filter((mark): mark is SignalMark => mark.x !== null);
  const outside = marks.length - drawn.length;

  return (
    <figure>
      <svg
        width={WIDTH}
        height={HEIGHT}
        role="img"
        aria-label={`Mcap teórico em SOL ao longo do tempo, de ${geometry.min.toFixed(2)} a ${geometry.max.toFixed(2)} SOL`}
        className="overflow-hidden text-fg-muted"
      >
        {overlay && <CurveLinesLayer overlay={overlay} toX={(x) => markX(geometry, x)} toY={(y) => markY(geometry, y)} />}
        <polyline points={geometry.linePoints} fill="none" stroke="currentColor" strokeWidth={1.5} />
        {drawn.map((mark) => (
          <line key={`${mark.label}-${mark.x}`} x1={mark.x} x2={mark.x} y1={0} y2={HEIGHT} className="text-warning" stroke="currentColor" strokeWidth={1} strokeDasharray="2 2">
            <title>{mark.label}</title>
          </line>
        ))}
      </svg>
      <figcaption className="mt-1 text-[11px] text-fg-subtle">
        Mcap teórico (SOL) · {geometry.min.toFixed(2)} a {geometry.max.toFixed(2)}
        {omitted > 0 ? ` · ${omitted} ponto(s) sem mcap omitido(s)` : ""}
        {drawn.length > 0 ? ` · marcas: ${drawn.map((m) => m.label).join(", ")}` : ""}
        {outside > 0 ? ` · ${outside} sinal(is) fora da janela do gráfico` : ""}
      </figcaption>
      {overlay && <CurveLinesCaption overlay={overlay} />}
    </figure>
  );
}
