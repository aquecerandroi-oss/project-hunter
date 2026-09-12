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
 */
import type { MemeSnapshotPoint } from "@/lib/api/meme-types";

export interface CurvePoint {
  x: number;
  y: number;
}

export interface CurveChartGeometry {
  linePoints: string;
  min: number;
  max: number;
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
  return { linePoints, min: minY, max: maxY };
}

export interface MemeCurveChartProps {
  snapshots: MemeSnapshotPoint[];
}

/** Newest-last order expected (chronological, left to right) -- callers pass `[...snapshots].reverse()` when the API returned newest-first (it does, `GET .../tokens/{mint}`). */
export function MemeCurveChart({ snapshots }: MemeCurveChartProps) {
  const withValue = snapshots.filter((s): s is MemeSnapshotPoint & { mcap_sol: string } => s.mcap_sol !== null);
  const omitted = snapshots.length - withValue.length;
  const points: CurvePoint[] = withValue.map((s) => ({ x: new Date(s.observed_at).getTime(), y: Number(s.mcap_sol) }));
  const geometry = curveChartGeometry(points);

  if (!geometry) {
    return <p className="text-xs text-fg-muted">Sem histórico suficiente para o gráfico de mcap.</p>;
  }

  return (
    <figure>
      <svg
        width={WIDTH}
        height={HEIGHT}
        role="img"
        aria-label={`Mcap teórico em SOL ao longo do tempo, de ${geometry.min.toFixed(2)} a ${geometry.max.toFixed(2)} SOL`}
        className="text-fg-muted"
      >
        <polyline points={geometry.linePoints} fill="none" stroke="currentColor" strokeWidth={1.5} />
      </svg>
      <figcaption className="mt-1 text-[11px] text-fg-subtle">
        Mcap teórico (SOL) · {geometry.min.toFixed(2)} a {geometry.max.toFixed(2)}
        {omitted > 0 ? ` · ${omitted} ponto(s) sem mcap omitido(s)` : ""}
      </figcaption>
    </figure>
  );
}
