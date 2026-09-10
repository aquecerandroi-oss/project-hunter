import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// `server-only` throws when imported outside Next's real "react-server"
// build condition, which Vitest never sets (see tests/invitations-actions.test.ts).
vi.mock("server-only", () => ({}));

const { resolveOrgContextMock, systemInfoMock, readyMock, getWorkersMock, getLatencyMock, refreshMock, useRouterMock } = vi.hoisted(
  () => ({
    resolveOrgContextMock: vi.fn(),
    systemInfoMock: vi.fn(),
    readyMock: vi.fn(),
    getWorkersMock: vi.fn(),
    getLatencyMock: vi.fn(),
    refreshMock: vi.fn(),
    useRouterMock: vi.fn(),
  }),
);

vi.mock("@/lib/api/org-context", () => ({ resolveOrgContext: resolveOrgContextMock }));
vi.mock("@/lib/api/system", () => ({
  systemInfo: systemInfoMock,
  ready: readyMock,
  getWorkers: getWorkersMock,
}));
vi.mock("@/lib/api/latency", () => ({ getLatency: getLatencyMock }));
vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("notFound() should not be called in these tests");
  },
  useRouter: useRouterMock,
}));
// `ReadinessPanel`'s manual "Atualizar" button calls the real Server Action
// module, which itself calls the real (mocked-above) `ready()` -- no need to
// mock `@/lib/api/system-actions` separately.
//
// H10: `AutoRefresh` used to be stubbed to `() => null` here, which proves
// neither that it mounts nor that it refreshes periodically -- the REAL
// component is used below, with only its own `next/navigation` dependency
// (`useRouter`) mocked, same as `auto-refresh.test.tsx`.

import SystemPage from "@/app/(app)/[orgSlug]/system/page";
import { DEFAULT_AUTO_REFRESH_INTERVAL_MS } from "@/lib/auto-refresh-interval";
import { ApiError } from "@/lib/api-error";
import type { LatencyOut } from "@/lib/api/latency-types";
import type { MembershipOut, SystemInfo, WorkerHeartbeat } from "@/lib/api/types";

function apiError(detail: string): ApiError {
  return new ApiError({ type: "about:blank", title: "Error", status: 503, detail });
}

const membership: MembershipOut = {
  onboarding: { completed: true, completed_at: "2026-01-01T00:00:00Z", workspace_id: "ws-1" },
  organization: {
    id: "org-1",
    slug: "acme",
    name: "Acme Capital",
    plan: "FREE",
    kill_switch_state: "ACTIVE",
    created_at: "2026-01-01T00:00:00Z",
  },
  role: "OWNER",
  status: "active",
};

const info: SystemInfo = {
  environment: "test",
  version: "1.0.0",
  git_sha: "abc123",
  features: {
    enable_live_trading: false,
    enable_social_intelligence: false,
    enable_onchain: false,
    enable_stripe: false,
    enable_llm_analysis: false,
    enable_arena: false,
    enable_backtests: false,
  },
};

const aliveWorker: WorkerHeartbeat = {
  role: "api",
  instance: "api-1",
  ts: new Date().toISOString(),
  last_success: new Date().toISOString(),
  errors: 0,
  version: "1.0.0",
  age_s: 3,
  status: "alive",
  last_event_at: null,
  ws_state: null,
  subscriptions: null,
  reconnects: null,
  markets_monitored: null,
  open_gaps: null,
};

const latencyOk: LatencyOut = {
  hops: [{ hop: "ingest", p50_s: 0.09, p95_s: 0.31, target_p50_s: 0.5, target_p95_s: 1.0, status: "ok" }],
  end_to_end: { hop: "end_to_end", p50_s: null, p95_s: null, target_p50_s: 5.0, target_p95_s: 10.0, status: "unknown" },
  generated_at: "2026-09-10T16:24:00Z",
};

beforeEach(() => {
  resolveOrgContextMock.mockReset().mockResolvedValue(membership);
  systemInfoMock.mockReset();
  readyMock.mockReset().mockResolvedValue({ database: true, redis: true });
  getWorkersMock.mockReset().mockResolvedValue([aliveWorker]);
  getLatencyMock.mockReset().mockResolvedValue(latencyOk);
  refreshMock.mockReset();
  useRouterMock.mockReset().mockReturnValue({ refresh: refreshMock });
});

afterEach(cleanup);

describe("SystemPage: one failing section must not take down the others (F3)", () => {
  it("still renders readiness and workers when systemInfo() rejects", async () => {
    systemInfoMock.mockRejectedValue(apiError("system info down"));

    const jsx = await SystemPage({ params: Promise.resolve({ orgSlug: "acme" }) });
    render(jsx);

    // The two sections driven by `systemInfo()` show their own honest failure...
    expect(screen.getAllByText(/indisponível: system info down/)).toHaveLength(2);
    // ...while readiness (an independent fetch) and workers (its own isolated fetch) still render real data.
    expect(screen.getAllByText("OK")).not.toHaveLength(0);
    expect(screen.getByText("api-1")).toBeInTheDocument();
    expect(screen.getByText("vivo")).toBeInTheDocument();
  });

  it("renders everything normally when all three fetches succeed", async () => {
    systemInfoMock.mockResolvedValue(info);

    const jsx = await SystemPage({ params: Promise.resolve({ orgSlug: "acme" }) });
    render(jsx);

    expect(screen.getByText("test")).toBeInTheDocument();
    expect(screen.getByText("api-1")).toBeInTheDocument();
    expect(screen.queryByText(/Indisponível:/)).not.toBeInTheDocument();
  });

  it("still shows the honest workers-down message when only getWorkers() fails, info still renders", async () => {
    systemInfoMock.mockResolvedValue(info);
    getWorkersMock.mockRejectedValue(apiError("workers down"));

    const jsx = await SystemPage({ params: Promise.resolve({ orgSlug: "acme" }) });
    render(jsx);

    expect(screen.getByText("test")).toBeInTheDocument();
    expect(screen.getByText(/Workers indisponível: workers down/)).toBeInTheDocument();
  });
});

describe("SystemPage: AutoRefresh actually mounts and keeps refreshing on this real page (H10)", () => {
  it("mounts the real AutoRefresh (not a () => null stub) and calls router.refresh() on an interval", async () => {
    systemInfoMock.mockResolvedValue(info);
    vi.useFakeTimers();

    const jsx = await SystemPage({ params: Promise.resolve({ orgSlug: "acme" }) });
    render(jsx);

    expect(useRouterMock).toHaveBeenCalled();
    act(() => {
      vi.advanceTimersByTime(DEFAULT_AUTO_REFRESH_INTERVAL_MS);
    });
    expect(refreshMock).toHaveBeenCalledTimes(1);

    vi.useRealTimers();
  });
});

describe("SystemPage: two 'execution' heartbeats -- the generic liveness row must never win over the paper aggregate (T3.44)", () => {
  it("picks hb:execution:paper (role+instance), not the generic hashed-instance liveness row that sorts before it", async () => {
    systemInfoMock.mockResolvedValue(info);
    const genericExecutionLiveness: WorkerHeartbeat = {
      role: "execution",
      // A real anonymized `hostname:pid` instance is a lowercase hex digest
      // (`anonymize_instance`), which always sorts before the literal
      // string "paper" -- this fixture reproduces that ordering, not just
      // the ordering of the array as written.
      instance: "3f997610fcc8",
      ts: new Date().toISOString(),
      last_success: null,
      errors: 0,
      version: "0.0.0",
      age_s: 1,
      status: "alive",
      last_event_at: null,
      ws_state: null,
      subscriptions: null,
      reconnects: null,
      markets_monitored: null,
      open_gaps: null,
    };
    const executionPaper: WorkerHeartbeat = {
      role: "execution",
      instance: "paper",
      ts: new Date().toISOString(),
      last_success: new Date().toISOString(),
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
      equity: "19333.0111164813",
      kill_switch: "ACTIVE",
      open_positions: 0,
      pending_requests: 0,
      unreadable_requests: 0,
      degraded_protections: 0,
      protection_delay_s: 0,
      last_mtm: new Date().toISOString(),
      last_protection: new Date().toISOString(),
      last_kill_switch_read: new Date().toISOString(),
      paper_autonomy: false,
    };
    // Sorted the way `scan_heartbeats` returns them: the hashed-instance row
    // first, "paper" second -- `.find()` must not stop at the first one.
    getWorkersMock.mockReset().mockResolvedValue([genericExecutionLiveness, executionPaper]);

    const jsx = await SystemPage({ params: Promise.resolve({ orgSlug: "acme" }) });
    render(jsx);

    expect(screen.getByText("19,333.01 USDT")).toBeInTheDocument();
    expect(screen.getByText("ATIVO")).toBeInTheDocument();
    expect(screen.getByText("Autonomia: desligada")).toBeInTheDocument();
    // The generic row has none of the T3.13 fields -- if it had won, every
    // one of these would read "indisponível" instead.
    expect(screen.queryAllByText("indisponível")).toHaveLength(0);
  });
});

describe("SystemPage: Latência section (T3.79) -- isolated the same way Workers/API info are", () => {
  it("renders the Latência panel with a real hop row when getLatency() succeeds", async () => {
    systemInfoMock.mockResolvedValue(info);

    const jsx = await SystemPage({ params: Promise.resolve({ orgSlug: "acme" }) });
    render(jsx);

    expect(screen.getByTestId("latency-panel")).toBeInTheDocument();
    expect(screen.getByTestId("latency-row-ingest")).toBeInTheDocument();
  });

  it("shows the honest 'Latência indisponível' box, without taking down Workers or API info, when getLatency() rejects", async () => {
    systemInfoMock.mockResolvedValue(info);
    getLatencyMock.mockRejectedValue(apiError("latency down"));

    const jsx = await SystemPage({ params: Promise.resolve({ orgSlug: "acme" }) });
    render(jsx);

    expect(screen.getByText(/Latência indisponível: latency down/)).toBeInTheDocument();
    expect(screen.queryByTestId("latency-panel")).not.toBeInTheDocument();
    expect(screen.getByText("test")).toBeInTheDocument();
    expect(screen.getByText("api-1")).toBeInTheDocument();
  });
});

describe("SystemPage: a 503 from getWorkers() is unavailable, never an empty-but-successful list (H3)", () => {
  it("renders the honest failure message, not WorkersTable's own 'Nenhum worker registrado' empty state", async () => {
    systemInfoMock.mockResolvedValue(info);
    getWorkersMock.mockRejectedValue(apiError("workers down"));

    const jsx = await SystemPage({ params: Promise.resolve({ orgSlug: "acme" }) });
    render(jsx);

    expect(screen.getByText(/Workers indisponível: workers down/)).toBeInTheDocument();
    expect(screen.queryByText(/Nenhum worker registrado/)).not.toBeInTheDocument();
  });
});

