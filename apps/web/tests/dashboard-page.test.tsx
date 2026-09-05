import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

const { resolveOrgContextMock, listWorkspacesMock, listMembersMock, getMarketStatusMock } = vi.hoisted(() => ({
  resolveOrgContextMock: vi.fn(),
  listWorkspacesMock: vi.fn(),
  listMembersMock: vi.fn(),
  getMarketStatusMock: vi.fn(),
}));

vi.mock("@/lib/api/org-context", () => ({ resolveOrgContext: resolveOrgContextMock }));
vi.mock("@/lib/api/workspaces", () => ({ listWorkspaces: listWorkspacesMock }));
vi.mock("@/lib/api/members", () => ({ listMembers: listMembersMock }));
vi.mock("@/lib/api/system", () => ({ getMarketStatus: getMarketStatusMock }));
vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("notFound() should not be called in these tests");
  },
}));
vi.mock("@clerk/nextjs", () => ({
  useAuth: () => ({ getToken: async () => null }),
}));
vi.mock("@/hooks/useMarketChannels", () => ({ useMarketChannels: () => ({ status: "closed", messages: {} }) }));

import DashboardPage from "@/app/(app)/[orgSlug]/dashboard/page";
import { ApiError } from "@/lib/api-error";
import type { MemberOut, MembershipOut, WorkspaceOut } from "@/lib/api/types";

function apiError(detail: string): ApiError {
  return new ApiError({ type: "about:blank", title: "Error", status: 503, detail });
}

function makeMember(userId: string): MemberOut {
  return {
    user_id: userId,
    email: `${userId}@acme.com`,
    display_name: userId,
    avatar_url: null,
    role: "VIEWER",
    status: "active",
    joined_at: "2026-01-01T00:00:00Z",
    created_at: "2026-01-01T00:00:00Z",
  };
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

const workspace: WorkspaceOut = {
  id: "ws-1",
  organization_id: "org-1",
  name: "Main",
  objective: "paper_trading",
  default_risk_profile_id: null,
  settings: { default_initial_capital: "10000", monitored_exchanges: ["binance"], risk_preset: "balanced" },
  created_at: "2026-01-01T00:00:00Z",
  onboarding_completed_at: "2026-01-01T00:00:00Z",
};

const marketStatus = {
  exchanges: [
    {
      exchange: "binance",
      ws_state: "connected",
      last_event_at: new Date().toISOString(),
      last_event_age_ms: 100,
      markets_monitored: 200,
      open_gaps: 0,
      reconnects: 0,
    },
  ],
  markets_monitored_total: 200,
  updated_at: new Date().toISOString(),
};

beforeEach(() => {
  resolveOrgContextMock.mockReset().mockResolvedValue(membership);
  listWorkspacesMock.mockReset();
  listMembersMock.mockReset();
  getMarketStatusMock.mockReset().mockResolvedValue(marketStatus);
});

afterEach(cleanup);

describe("DashboardPage: one failing section must not take down the others (F3)", () => {
  it("still renders members and market status when listWorkspaces() rejects", async () => {
    listWorkspacesMock.mockRejectedValue(apiError("workspaces down"));
    listMembersMock.mockResolvedValue({ items: [makeMember("m1"), makeMember("m2")], next_cursor: null });

    const jsx = await DashboardPage({ params: Promise.resolve({ orgSlug: "acme" }) });
    render(jsx);

    expect(screen.getByText(/Workspace indisponível: workspaces down/)).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("binance")).toBeInTheDocument();
  });

  it("still renders the workspace and market status when listMembers() rejects", async () => {
    listWorkspacesMock.mockResolvedValue({ items: [workspace], next_cursor: null });
    listMembersMock.mockRejectedValue(apiError("members down"));

    const jsx = await DashboardPage({ params: Promise.resolve({ orgSlug: "acme" }) });
    render(jsx);

    expect(screen.getByText(/Membros indisponível: members down/)).toBeInTheDocument();
    expect(screen.getByText("binance")).toBeInTheDocument();
  });

  it("renders everything normally when all fetches succeed", async () => {
    listWorkspacesMock.mockResolvedValue({ items: [workspace], next_cursor: null });
    listMembersMock.mockResolvedValue({ items: [makeMember("m1")], next_cursor: null });

    const jsx = await DashboardPage({ params: Promise.resolve({ orgSlug: "acme" }) });
    render(jsx);

    expect(screen.queryByText(/indisponível/i)).not.toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
  });
});

describe("DashboardPage: a 503 from getMarketStatus() is unavailable, never a healthy-looking empty market (H3)", () => {
  it("shows the honest 'status indisponível' message, not '0 exchanges' or a fabricated count", async () => {
    listWorkspacesMock.mockResolvedValue({ items: [workspace], next_cursor: null });
    listMembersMock.mockResolvedValue({ items: [makeMember("m1")], next_cursor: null });
    getMarketStatusMock.mockRejectedValue(apiError("market-status down"));

    const jsx = await DashboardPage({ params: Promise.resolve({ orgSlug: "acme" }) });
    render(jsx);

    expect(screen.getByText(/Mercados: status indisponível no momento/)).toBeInTheDocument();
    expect(screen.queryByText("binance")).not.toBeInTheDocument();
    expect(screen.queryByText("Market worker: sem heartbeat")).not.toBeInTheDocument();
  });
});
