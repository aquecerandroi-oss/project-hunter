import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// `server-only` throws outside Next's real "react-server" build condition
// (see tests/markets-page.test.tsx and tests/invitations-actions.test.ts).
vi.mock("server-only", () => ({}));

const { resolveOrgContextMock, getLabSummaryMock, listLabVersionsMock, getLabSignalsMock } = vi.hoisted(() => ({
  resolveOrgContextMock: vi.fn(),
  getLabSummaryMock: vi.fn(),
  listLabVersionsMock: vi.fn(),
  getLabSignalsMock: vi.fn(),
}));

vi.mock("@/lib/api/org-context", () => ({ resolveOrgContext: resolveOrgContextMock }));
vi.mock("@/lib/api/lab", () => ({
  getLabSummary: getLabSummaryMock,
  listLabVersions: listLabVersionsMock,
  getLabSignals: getLabSignalsMock,
}));
vi.mock("@/lib/api/lab-actions", () => ({
  loadLabSignalsAction: vi.fn(),
  loadLabSignalEnvelopeAction: vi.fn(),
  resolveMarketHrefAction: vi.fn(),
}));
vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("notFound() should not be called in these tests");
  },
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/acme/lab",
}));

import LabPage from "@/app/(app)/[orgSlug]/lab/page";
import { ApiError } from "@/lib/api-error";
import type { MembershipOut } from "@/lib/api/types";
import { exampleSignal, exampleSummary, makeVersionSummary } from "@/tests/fixtures/lab";

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

function renderPage(searchParams: Record<string, string> = {}) {
  return LabPage({
    params: Promise.resolve({ orgSlug: "acme" }),
    searchParams: Promise.resolve(searchParams),
  });
}

beforeEach(() => {
  resolveOrgContextMock.mockReset().mockResolvedValue(membership);
  getLabSummaryMock.mockReset();
  listLabVersionsMock.mockReset().mockResolvedValue({ items: [] });
  getLabSignalsMock.mockReset().mockResolvedValue({ items: [], next_cursor: null });
});

afterEach(cleanup);

describe("LabPage: renders the real contract fixture", () => {
  it("shows the fixed SOMBRA label, as_of, a version card and the signals table", async () => {
    getLabSummaryMock.mockResolvedValue(exampleSummary());
    getLabSignalsMock.mockResolvedValue({ items: [exampleSignal()], next_cursor: null });

    const jsx = await renderPage();
    render(jsx);

    expect(screen.getByText(/SOMBRA — hipotético, sem capital/)).toBeInTheDocument();
    // The fixed top banner (mandatory, brief S3b) shows the costs when every
    // version in view agrees; each version card also always shows its own
    // `coverage.assumed_costs` (Astra's S3b review: never let the card's
    // costs depend on the banner) -- with a single version in this fixture
    // both legitimately render the same string. Scoped to the banner
    // specifically (Astra's diff review nice-to-have: don't let a looser
    // "at least one" check silently pass if the banner itself lost the text),
    // and asserting the exact required phrase (code-reviewer must-fix): the
    // "custos assumidos:" prefix is part of the brief's literal wording, not
    // just the numbers that follow it.
    expect(
      within(screen.getByTestId("lab-header")).getByText(
        "SOMBRA — hipotético, sem capital, custos assumidos: spread 2 bps, slippage 5 bps/lado, taxa 4 bps/lado",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("momentum / v2")).toBeInTheDocument();
    expect(screen.getByText("AAAAUSDT")).toBeInTheDocument();
  });

  it("defaults to window=30d and cohort=prospective when no filters are given", async () => {
    getLabSummaryMock.mockResolvedValue(exampleSummary());
    await renderPage();
    expect(getLabSummaryMock).toHaveBeenCalledWith({ window: "30d", cohort: "prospective" });
  });

  it("never claims a shared cost banner when versions disagree (Astra's diff review nice-to-have)", async () => {
    const cheaper = makeVersionSummary({
      strategy_version_id: "v3-id",
      version: "v3",
      coverage: {
        ...makeVersionSummary().coverage,
        assumed_costs: { assumed_spread_bps: "1", slippage_bps: "2", fee_bps: "2", max_entry_delay_s: 120 },
      },
    });
    getLabSummaryMock.mockResolvedValue(exampleSummary({ versions: [makeVersionSummary(), cheaper] }));

    const jsx = await renderPage();
    render(jsx);

    // The banner never picks one version's numbers when they disagree.
    expect(
      within(screen.getByTestId("lab-header")).getByText(/discriminados por versão/),
    ).toBeInTheDocument();
    // Each card still states its own real numbers -- never left to the banner.
    expect(screen.getByText(/spread 2 bps, slippage 5 bps\/lado, taxa 4 bps\/lado/)).toBeInTheDocument();
    expect(screen.getByText(/spread 1 bps, slippage 2 bps\/lado, taxa 2 bps\/lado/)).toBeInTheDocument();
  });
});

describe("LabPage: 0 versions is a result, not an error", () => {
  it("shows the honest empty-versions state, still inside a successful page", async () => {
    getLabSummaryMock.mockResolvedValue(exampleSummary({ versions: [] }));
    const jsx = await renderPage();
    render(jsx);
    expect(screen.getByText(/Nenhuma versão de estratégia ativada ainda/)).toBeInTheDocument();
  });
});

describe("LabPage: 503 reads as 'sem verificação', never as '0'", () => {
  it("shows LabError instead of an empty table when the summary fetch fails", async () => {
    getLabSummaryMock.mockRejectedValue(
      new ApiError({ type: "about:blank/lab-unavailable", title: "Service Unavailable", status: 503, detail: "Shadow Lab data is temporarily unavailable." }),
    );
    const jsx = await renderPage();
    render(jsx);
    expect(screen.getByText(/sem verificação/)).toBeInTheDocument();
    expect(screen.getByText(/Shadow Lab data is temporarily unavailable/)).toBeInTheDocument();
  });
});
