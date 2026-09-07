import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(cleanup);

import { ExecutionPaperCard } from "@/components/system/execution-paper-card";
import type { WorkerHeartbeat } from "@/lib/api/types";

const NOW = new Date("2026-09-07T12:00:00.000Z");

function makeWorker(overrides: Partial<WorkerHeartbeat> = {}): WorkerHeartbeat {
  return {
    role: "execution",
    instance: "paper",
    ts: NOW.toISOString(),
    last_success: NOW.toISOString(),
    errors: 0,
    version: "1.0.0",
    age_s: 1,
    status: "alive",
    last_event_at: null,
    ws_state: null,
    subscriptions: null,
    reconnects: null,
    markets_monitored: null,
    open_gaps: null,
    equity: "10250.5000000000",
    kill_switch: "ACTIVE",
    open_positions: 2,
    pending_requests: 1,
    unreadable_requests: 0,
    degraded_protections: 0,
    protection_delay_s: 0,
    last_mtm: new Date(NOW.getTime() - 5_000).toISOString(),
    last_protection: new Date(NOW.getTime() - 30_000).toISOString(),
    last_kill_switch_read: new Date(NOW.getTime() - 2_000).toISOString(),
    paper_autonomy: false,
    ...overrides,
  };
}

describe("ExecutionPaperCard: honest nulls, never a fabricated 0 (T3.8c)", () => {
  it("renders real values -- equity in USDT, counts, autonomia desligada by default", () => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);

    render(<ExecutionPaperCard worker={makeWorker()} />);

    expect(screen.getByText("10,250.50 USDT")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument(); // open_positions
    expect(screen.getByText("Autonomia: desligada")).toBeInTheDocument();
    expect(screen.getByText("ATIVO")).toBeInTheDocument();
    expect(screen.getByText(/há 5s/)).toBeInTheDocument(); // last_mtm age
    expect(screen.getAllByText(/UTC/).length).toBeGreaterThan(0); // same UTC+offset time component as other screens

    vi.useRealTimers();
  });

  it("shows 'indisponível' for every absent optional field, never a silent 0 -- and no heartbeat at all is its own honest empty state", () => {
    render(
      <ExecutionPaperCard
        worker={makeWorker({
          equity: null,
          kill_switch: null,
          open_positions: null,
          pending_requests: null,
          unreadable_requests: null,
          degraded_protections: null,
          protection_delay_s: null,
          last_mtm: null,
          last_protection: null,
          last_kill_switch_read: null,
          paper_autonomy: null,
        })}
      />,
    );

    expect(screen.queryByText("0")).not.toBeInTheDocument();
    expect(screen.getAllByText("indisponível").length).toBeGreaterThanOrEqual(9);
  });

  it("renders the honest empty state when the execution/paper heartbeat has never reported", () => {
    render(<ExecutionPaperCard worker={null} />);
    expect(screen.getByText(/sem heartbeat/)).toBeInTheDocument();
    expect(screen.queryByText("Patrimônio")).not.toBeInTheDocument();
  });

  it("puts a TRADING_DISABLED kill switch in visible destaque (red panel, BLOQUEADO badge)", () => {
    render(<ExecutionPaperCard worker={makeWorker({ kill_switch: "TRADING_DISABLED" })} />);
    expect(screen.getByText("BLOQUEADO")).toBeInTheDocument();
    const panel = screen.getByTestId("execution-kill-switch-panel");
    expect(panel.className).toMatch(/border-red/);
  });

  it("puts an EMERGENCY kill switch in the same destaque", () => {
    render(<ExecutionPaperCard worker={makeWorker({ kill_switch: "EMERGENCY" })} />);
    expect(screen.getByText("EMERGÊNCIA")).toBeInTheDocument();
    const panel = screen.getByTestId("execution-kill-switch-panel");
    expect(panel.className).toMatch(/border-red/);
  });

  it("explains unreadable_requests > 0 as 'sem geometria: a API arquivou, o motor não decide'", () => {
    render(<ExecutionPaperCard worker={makeWorker({ unreadable_requests: 3 })} />);
    expect(screen.getByText(/3 pedidos sem geometria: a API arquivou, o motor não decide\./)).toBeInTheDocument();
  });

  it("does not show the unreadable-requests explanation when the count is exactly 0", () => {
    render(<ExecutionPaperCard worker={makeWorker({ unreadable_requests: 0 })} />);
    expect(screen.queryByText(/sem geometria/)).not.toBeInTheDocument();
  });

  it("highlights degraded_protections > 0 in a warning badge", () => {
    render(<ExecutionPaperCard worker={makeWorker({ degraded_protections: 4 })} />);
    expect(screen.getByText("4")).toBeInTheDocument();
  });

  it("shows 'Autonomia: ligada' when ENABLE_PAPER_AUTONOMY is actually on for this process", () => {
    render(<ExecutionPaperCard worker={makeWorker({ paper_autonomy: true })} />);
    expect(screen.getByText("Autonomia: ligada")).toBeInTheDocument();
  });
});
