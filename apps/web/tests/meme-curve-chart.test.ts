import { describe, expect, it } from "vitest";

import { curveChartGeometry } from "@/components/meme/meme-curve-chart";

describe("curveChartGeometry: pure time-scaled math for the mcap chart", () => {
  it("returns null for fewer than two points, never drawing a line from nothing", () => {
    expect(curveChartGeometry([])).toBeNull();
    expect(curveChartGeometry([{ x: 0, y: 1 }])).toBeNull();
  });

  it("scales x by real elapsed time, not by index -- a late-arriving point sits far to the right", () => {
    const geometry = curveChartGeometry([
      { x: 0, y: 1 },
      { x: 10, y: 2 },
      { x: 1000, y: 3 },
    ]);
    const xs = geometry?.linePoints.split(" ").map((pair) => Number(pair.split(",")[0])) ?? [];
    // The gap between point 2 (x=10) and point 3 (x=1000) is ~99x the gap
    // between point 1 (x=0) and point 2 (x=10) -- the drawn x-gap must
    // reflect that, never look like three evenly-spaced samples.
    const firstGap = (xs[1] ?? 0) - (xs[0] ?? 0);
    const secondGap = (xs[2] ?? 0) - (xs[1] ?? 0);
    expect(secondGap).toBeGreaterThan(firstGap * 50);
  });

  it("flips Y so the highest mcap sits at the top of the box (SVG grows downward)", () => {
    const geometry = curveChartGeometry([
      { x: 0, y: 0 },
      { x: 1, y: 10 },
    ]);
    const points = geometry?.linePoints.split(" ").map((pair) => pair.split(",").map(Number)) ?? [];
    const ys = points.map(([, y]) => y as number);
    expect(ys[1]).toBeLessThan(ys[0] as number); // higher mcap (index 1) draws nearer the top
  });

  it("centers a flat series instead of dividing by zero", () => {
    const geometry = curveChartGeometry([
      { x: 0, y: 5 },
      { x: 1, y: 5 },
    ]);
    const points = geometry?.linePoints.split(" ").map((pair) => pair.split(",").map(Number)) ?? [];
    const ys = points.map(([, y]) => y as number);
    expect(ys.every((y) => y === 32)).toBe(true); // HEIGHT / 2
  });

  it("reports the real min/max of the series", () => {
    const geometry = curveChartGeometry([
      { x: 0, y: 2.5 },
      { x: 1, y: 9.1 },
    ]);
    expect(geometry?.min).toBe(2.5);
    expect(geometry?.max).toBe(9.1);
  });
});
