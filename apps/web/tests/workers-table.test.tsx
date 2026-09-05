import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

afterEach(cleanup);

import { WorkersTable } from "@/components/system/workers-table";
import type { WorkerHeartbeat } from "@/lib/api/types";

const genericWorker: WorkerHeartbeat = {
  role: "api",
  instance: "api-1",
  ts: new Date().toISOString(),
  last_success: new Date().toISOString(),
  errors: 0,
  version: "1.0.0",
  age_s: 5,
  status: "alive",
  last_event_at: null,
  ws_state: null,
  subscriptions: null,
  reconnects: null,
  markets_monitored: null,
  open_gaps: null,
};

const marketWorker: WorkerHeartbeat = {
  role: "market",
  instance: "binance",
  ts: new Date().toISOString(),
  last_success: new Date().toISOString(),
  errors: 0,
  version: "1.0.0",
  age_s: 5,
  status: "alive",
  last_event_at: new Date().toISOString(),
  ws_state: "connected",
  subscriptions: 400,
  reconnects: 1,
  markets_monitored: 200,
  open_gaps: 0,
};

describe("WorkersTable: real heartbeats, no invented processes", () => {
  it("renders a worker row with role, status and version", () => {
    render(<WorkersTable workers={[genericWorker]} />);
    expect(screen.getByText("api")).toBeInTheDocument();
    expect(screen.getByText("alive")).toBeInTheDocument();
    expect(screen.getByText("1.0.0")).toBeInTheDocument();
  });

  it("derives the exchange heartbeat row from the market role's own ws_state/markets_monitored", () => {
    render(<WorkersTable workers={[genericWorker, marketWorker]} />);
    expect(screen.getAllByText("binance").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("CONNECTED")).toBeInTheDocument();
    expect(screen.getByText("200")).toBeInTheDocument();
  });

  it("shows an honest empty row instead of an empty table when nothing has reported", () => {
    render(<WorkersTable workers={[]} />);
    expect(screen.getByText(/Nenhum worker registrado ainda/)).toBeInTheDocument();
    expect(screen.getByText(/Nenhuma exchange reportando heartbeat/)).toBeInTheDocument();
  });
});
