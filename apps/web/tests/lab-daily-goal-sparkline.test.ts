import { describe, expect, it } from "vitest";

import { sparklineGeometry } from "@/components/lab/lab-daily-goal-sparkline";

describe("sparklineGeometry: pure scale math for the 30-day unique-R sparkline", () => {
  it("returns empty geometry for no points, never dividing by a zero-length array", () => {
    const geometry = sparklineGeometry([]);
    expect(geometry).toEqual({ linePoints: "", zeroLinePoints: null, min: 0, max: 0 });
  });

  it("centers a single (or perfectly flat) series on the middle row instead of dividing by zero", () => {
    const geometry = sparklineGeometry([2, 2, 2]);
    const ys = geometry.linePoints.split(" ").map((pair) => Number(pair.split(",")[1]));
    expect(ys.every((y) => y === 20)).toBe(true); // HEIGHT / 2
  });

  it("flips Y so the highest value sits at the top of the box (SVG grows downward)", () => {
    const geometry = sparklineGeometry([0, 1, 2]);
    const points = geometry.linePoints.split(" ").map((pair) => pair.split(",").map(Number));
    const ys = points.map(([, y]) => y);
    expect(ys[0]).toBeGreaterThan(ys[2] as number); // min (0) at the bottom, max (2) at the top
  });

  it("spaces points evenly across the fixed width", () => {
    const geometry = sparklineGeometry([0, 1, 2, 3]);
    const xs = geometry.linePoints.split(" ").map((pair) => Number(pair.split(",")[0]));
    expect(xs).toEqual([0, 280 / 3, (280 / 3) * 2, 280]);
  });

  it("only draws a zero baseline when the series actually crosses zero", () => {
    expect(sparklineGeometry([1, 2, 3]).zeroLinePoints).toBeNull(); // all positive
    expect(sparklineGeometry([-1, -2]).zeroLinePoints).toBeNull(); // all negative
    expect(sparklineGeometry([-1, 0, 2]).zeroLinePoints).not.toBeNull(); // crosses zero
  });

  it("reports the real min/max of the series", () => {
    const geometry = sparklineGeometry([-2.5, 0, 4.25]);
    expect(geometry.min).toBe(-2.5);
    expect(geometry.max).toBe(4.25);
  });
});
