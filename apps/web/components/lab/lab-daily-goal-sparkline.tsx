/**
 * "sparkline de 30 dias do R único" (brief T3.78): a calm, discrete, no-library
 * SVG line -- same convention as `components/opportunities/why-history.tsx`'s
 * `Sparkline` (docs/DESIGN.md §2 "movimento calmo"), extended with a zero
 * baseline since `unique_r` can be negative (a losing day), which that
 * simpler score sparkline never had to represent. `stroke="currentColor"`
 * (no hardcoded hex) makes it theme-aware: it inherits whatever `text-*`
 * color class wraps it, so it renders correctly in both the dark and the
 * light theme without its own light/dark branch.
 */
import type { DailyGoalSeriesPoint } from "@/lib/api/lab-daily-goal-types";

export interface SparklineGeometry {
  /** SVG `points` attribute for the value polyline, chronological left-to-right. */
  linePoints: string;
  /** SVG `points` for a light zero-baseline reference, only rendered when the series actually crosses zero (min < 0 < max) -- otherwise a flat top/bottom-edge line would say nothing real. */
  zeroLinePoints: string | null;
  min: number;
  max: number;
}

const WIDTH = 280;
const HEIGHT = 40;

function toNumber(value: string): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

/**
 * Pure scale math (unit-tested on its own in
 * `tests/lab-daily-goal-sparkline.test.ts`): maps `values` (chronological,
 * oldest first) onto a `WIDTH`x`HEIGHT` box, flipping Y (SVG grows downward,
 * a chart's "up" must not). A flat series (`min === max`, incl. a single
 * point) centers on the middle row rather than dividing by zero.
 */
export function sparklineGeometry(values: number[]): SparklineGeometry {
  if (values.length === 0) return { linePoints: "", zeroLinePoints: null, min: 0, max: 0 };
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const step = values.length > 1 ? WIDTH / (values.length - 1) : 0;
  const y = (v: number): number => (max === min ? HEIGHT / 2 : HEIGHT - ((v - min) / span) * HEIGHT);
  const linePoints = values.map((v, i) => `${i * step},${y(v)}`).join(" ");
  const crossesZero = min < 0 && max > 0;
  const zeroLinePoints = crossesZero ? `0,${y(0)} ${WIDTH},${y(0)}` : null;
  return { linePoints, zeroLinePoints, min, max };
}

export interface LabDailyGoalSparklineProps {
  series: DailyGoalSeriesPoint[];
}

/** Unique R over the last 30 days (`series_30d`, already oldest-first per the frozen schema's own §1 note "do dia -29 ao dia consultado"). Renders nothing (an honest empty box, no invented line) when there are fewer than 2 points to draw a line between. */
export function LabDailyGoalSparkline({ series }: LabDailyGoalSparklineProps) {
  if (series.length < 2) {
    return <p className="text-xs text-fg-muted">Sem histórico suficiente para o gráfico de 30 dias.</p>;
  }
  const values = series.map((p) => toNumber(p.unique_r));
  const { linePoints, zeroLinePoints, min, max } = sparklineGeometry(values);
  return (
    <figure>
      <svg
        width={WIDTH}
        height={HEIGHT}
        role="img"
        aria-label={`R único por dia, últimos 30 dias, de ${min.toFixed(2)}R a ${max.toFixed(2)}R`}
        className="text-fg-muted"
      >
        {zeroLinePoints && <polyline points={zeroLinePoints} fill="none" stroke="currentColor" strokeWidth={1} strokeDasharray="2 3" opacity={0.5} />}
        <polyline points={linePoints} fill="none" stroke="currentColor" strokeWidth={1.5} />
      </svg>
      <figcaption className="mt-1 text-[11px] text-fg-subtle">
        30 dias · R único/dia · {min.toFixed(2)}R a {max.toFixed(2)}R
      </figcaption>
    </figure>
  );
}
