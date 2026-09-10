import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

afterEach(cleanup);

import { LatencyPanel } from "@/components/system/latency-panel";
import type { LatencyHop, LatencyOut } from "@/lib/api/latency-types";

function hop(overrides: Partial<LatencyHop> = {}): LatencyHop {
  return {
    hop: "ingest",
    p50_s: 0.09,
    p95_s: 0.31,
    target_p50_s: 0.5,
    target_p95_s: 1.0,
    status: "ok",
    ...overrides,
  };
}

function makeData(overrides: Partial<LatencyOut> = {}): LatencyOut {
  return {
    hops: [
      hop({ hop: "ingest", p50_s: 0.09, p95_s: 0.31, status: "ok" }),
      hop({ hop: "flush", p50_s: 1.03, p95_s: 3.9, target_p50_s: 0.5, target_p95_s: 1.0, status: "critical" }),
      hop({ hop: "decision", p50_s: 45, p95_s: 180, target_p50_s: 5, target_p95_s: 20, status: "critical" }),
      hop({ hop: "admission", p50_s: null, p95_s: null, target_p50_s: 1, target_p95_s: 2, status: "unknown" }),
      hop({ hop: "fill", p50_s: null, p95_s: null, target_p50_s: 1, target_p95_s: 2, status: "unknown" }),
    ],
    end_to_end: { hop: "end_to_end", p50_s: null, p95_s: null, target_p50_s: 5, target_p95_s: 10, status: "unknown" },
    generated_at: "2026-09-10T16:24:00Z",
    ...overrides,
  };
}

describe("LatencyPanel: one row per hop, a red hop cannot be scrolled past unnoticed (T3.79, Everton: 'quero tudo instantâneo')", () => {
  it("renders a row for every hop plus the end-to-end summary row", () => {
    render(<LatencyPanel data={makeData()} />);

    expect(screen.getByTestId("latency-row-ingest")).toBeInTheDocument();
    expect(screen.getByTestId("latency-row-flush")).toBeInTheDocument();
    expect(screen.getByTestId("latency-row-decision")).toBeInTheDocument();
    expect(screen.getByTestId("latency-row-admission")).toBeInTheDocument();
    expect(screen.getByTestId("latency-row-fill")).toBeInTheDocument();
    expect(screen.getByTestId("latency-row-end_to_end")).toBeInTheDocument();
  });

  it("shows a real ok hop's p50/p95 as numbers with unit, never as a plain fabricated string", () => {
    render(<LatencyPanel data={makeData()} />);
    const row = screen.getByTestId("latency-row-ingest");
    expect(row.textContent).toContain("0.09s");
    expect(row.textContent).toContain("0.31s");
    expect(row.textContent).toContain("OK");
  });

  it("tints a critical row's background and bolds its numbers red, plus a warning icon -- never only a badge", () => {
    render(<LatencyPanel data={makeData()} />);
    const row = screen.getByTestId("latency-row-flush");
    expect(row.className).toMatch(/bg-red-soft/);
    expect(row.textContent).toContain("Crítico");
    expect(row.querySelector("svg")).not.toBeNull();
  });

  it("never prints a p50/p95 number for an unknown hop -- 'sem medição: <motivo>' instead, in the merged cell that would otherwise hold those two numbers", () => {
    render(<LatencyPanel data={makeData()} />);
    const row = screen.getByTestId("latency-row-admission");
    const mergedCell = row.querySelector("td[colspan]");
    expect(mergedCell?.textContent).toBe("sem medição: o heartbeat do execution-worker ainda não reporta este dado");
    expect(mergedCell?.textContent).not.toMatch(/\d/);
    // The row still legitimately shows its *target* budget as numbers (1.00s / 2.00s) -- only the measured p50/p95 cell is suppressed.
    expect(row.textContent).toContain("1.00s / 2.00s");
  });

  it("shows targets and the Brasília 'consultado em' timestamp", () => {
    render(<LatencyPanel data={makeData()} />);
    expect(screen.getByTestId("latency-row-ingest").textContent).toContain("0.50s / 1.00s");
    expect(screen.getByText(/Consultado em/)).toBeInTheDocument();
    expect(screen.getByTitle("2026-09-10T16:24:00Z")).toBeInTheDocument();
  });

  it("does not tint an ok or unknown row red", () => {
    render(<LatencyPanel data={makeData()} />);
    expect(screen.getByTestId("latency-row-ingest").className).not.toMatch(/bg-red-soft/);
    expect(screen.getByTestId("latency-row-admission").className).not.toMatch(/bg-red-soft/);
  });
});
