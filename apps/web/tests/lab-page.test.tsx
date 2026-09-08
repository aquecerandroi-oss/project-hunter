import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// `server-only` throws outside Next's real "react-server" build condition
// (see tests/markets-page.test.tsx and tests/invitations-actions.test.ts).
vi.mock("server-only", () => ({}));

const {
  resolveOrgContextMock,
  getLabSummaryMock,
  listLabVersionsMock,
  getLabSignalsMock,
  getLabScoreboardMock,
  getLabCurveMock,
  listPortfoliosMock,
  getPortfolioSummaryMock,
} = vi.hoisted(() => ({
  resolveOrgContextMock: vi.fn(),
  getLabSummaryMock: vi.fn(),
  listLabVersionsMock: vi.fn(),
  getLabSignalsMock: vi.fn(),
  getLabScoreboardMock: vi.fn(),
  getLabCurveMock: vi.fn(),
  listPortfoliosMock: vi.fn(),
  getPortfolioSummaryMock: vi.fn(),
}));

vi.mock("@/lib/api/org-context", () => ({ resolveOrgContext: resolveOrgContextMock }));
vi.mock("@/lib/api/lab", () => ({
  getLabSummary: getLabSummaryMock,
  listLabVersions: listLabVersionsMock,
  getLabSignals: getLabSignalsMock,
  getLabScoreboard: getLabScoreboardMock,
  getLabCurve: getLabCurveMock,
}));
vi.mock("@/lib/api/portfolio", () => ({
  listPortfolios: listPortfoliosMock,
  getPortfolioSummary: getPortfolioSummaryMock,
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

// `LabCurveChart` (T3.18) creates a real `lightweight-charts` chart when it
// has at least one drawable series -- mocked the same way
// `tests/portfolio-equity-chart.test.tsx` mocks it, so this page test never
// depends on a real canvas.
vi.mock("lightweight-charts", () => ({
  LineSeries: "line-series-type",
  createChart: vi.fn(() => ({ addSeries: vi.fn(() => ({ setData: vi.fn(), applyOptions: vi.fn() })), applyOptions: vi.fn(), remove: vi.fn() })),
}));

import LabPage from "@/app/(app)/[orgSlug]/lab/page";
import { ApiError } from "@/lib/api-error";
import type { MembershipOut } from "@/lib/api/types";
import { exampleCurve, exampleScoreboardRow, exampleSignal, exampleSummary, makeVersionSummary } from "@/tests/fixtures/lab";
import { exampleSignalsPageRange, exampleSignalsTotals } from "@/tests/fixtures/lab-pagination";

const EMPTY_SIGNALS_PAGE = { items: [], next_cursor: null, totals: { closed: 0, open: 0, pending: 0, all: 0 }, page: { from: 0, to: 0 } };

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
  getLabSignalsMock.mockReset().mockResolvedValue(EMPTY_SIGNALS_PAGE);
  // Empty Placar by default (brief T3.18) -- exercised by every existing
  // test unless a case below overrides it.
  getLabScoreboardMock.mockReset().mockResolvedValue({ as_of: "2026-09-08T12:00:00Z", label: "SOMBRA — hipotético, sem capital, custos assumidos", rows: [] });
  getLabCurveMock.mockReset().mockResolvedValue(exampleCurve());
  // No wallet by default -- the reference-ruler fallback (brief T3.17) is
  // exercised by every existing test unless a case below overrides it.
  listPortfoliosMock.mockReset().mockResolvedValue({ items: [], next_cursor: null });
  getPortfolioSummaryMock.mockReset();
});

afterEach(cleanup);

describe("LabPage: renders the real contract fixture", () => {
  it("shows the fixed SOMBRA label, as_of, a version card and the signals table", async () => {
    getLabSummaryMock.mockResolvedValue(exampleSummary());
    getLabSignalsMock.mockResolvedValue({ items: [exampleSignal()], next_cursor: null, totals: exampleSignalsTotals({ closed: 1, open: 0, pending: 0, all: 1 }), page: exampleSignalsPageRange({ to: 1 }) });

    const jsx = await renderPage();
    render(jsx);

    expect(screen.getByText("SOMBRA — simulação sobre dado real. Nada foi comprado ou vendido.")).toBeInTheDocument();
    // The fixed top banner (mandatory, brief S3b, compacted by T3.24b item
    // [1]) shows the costs when every version in view agrees; each version
    // card also always shows its own `coverage.assumed_costs` (Astra's S3b
    // review: never let the card's costs depend on the banner) -- with a
    // single version in this fixture both legitimately render the same
    // string.
    expect(
      within(screen.getByTestId("lab-header")).getByText(
        /custos assumidos: spread 2 bps, slippage 5 bps\/lado, taxa 4 bps\/lado/,
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
    expect(screen.getByText(/Nenhuma versão de estratégia ativa nesta janela e coorte/)).toBeInTheDocument();
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

describe("LabPage: the money ruler (brief T3.17)", () => {
  it("falls back to the labelled 10.000 USDT reference wallet when the organization has no principal paper wallet", async () => {
    getLabSummaryMock.mockResolvedValue(exampleSummary());
    listPortfoliosMock.mockResolvedValue({ items: [], next_cursor: null });

    const jsx = await renderPage();
    render(jsx);

    expect(screen.getByText(/simulação sobre dado real\. Nada foi comprado ou vendido\./)).toBeInTheDocument();
    expect(screen.getByTestId("lab-money-ruler")).toHaveTextContent("Régua: 0,25% de 10,000.00 USDT (carteira de referência, sem carteira aberta) = 25.00 USDT por operação");
  });

  it("falls back to the reference wallet when the organization has a wallet but it is not the principal paper one (is_arena)", async () => {
    getLabSummaryMock.mockResolvedValue(exampleSummary());
    listPortfoliosMock.mockResolvedValue({
      items: [{ id: "arena-1", workspace_id: "ws-1", name: "Arena", type: "paper", status: "active", is_arena: true, base_currency: "USDT", created_at: "2026-01-01T00:00:00Z" }],
      next_cursor: null,
    });

    const jsx = await renderPage();
    render(jsx);

    expect(getPortfolioSummaryMock).not.toHaveBeenCalled();
    expect(screen.getByTestId("lab-money-ruler")).toHaveTextContent("carteira de referência, sem carteira aberta");
  });

  it("uses the real principal paper wallet's equity when it exists (the 'ever' wallet example from the brief)", async () => {
    getLabSummaryMock.mockResolvedValue(exampleSummary());
    listPortfoliosMock.mockResolvedValue({
      items: [{ id: "ever-1", workspace_id: "ws-1", name: "ever", type: "paper", status: "active", is_arena: false, base_currency: "USDT", created_at: "2026-01-01T00:00:00Z" }],
      next_cursor: null,
    });
    getPortfolioSummaryMock.mockResolvedValue({ equity: "19333.01", brl: { equity_brl: "115998.06" } });

    const jsx = await renderPage();
    render(jsx);

    expect(getPortfolioSummaryMock).toHaveBeenCalledWith("org-1", "ever-1");
    expect(screen.getByTestId("lab-money-ruler")).toHaveTextContent(
      "Régua: 0,25% de 19,333.01 USDT (carteira principal (paper)) = 48.33 USDT por operação",
    );
  });

  it("falls back to the reference wallet, without failing the page, when the portfolio lookup itself errors", async () => {
    getLabSummaryMock.mockResolvedValue(exampleSummary());
    listPortfoliosMock.mockRejectedValue(new Error("network down"));

    const jsx = await renderPage();
    render(jsx);

    expect(screen.getByTestId("lab-money-ruler")).toHaveTextContent("carteira de referência, sem carteira aberta");
    // A ruler-only failure is not a Lab failure -- the rest of the page still renders.
    expect(screen.queryByText(/sem verificação/)).not.toBeInTheDocument();
  });
});

describe("LabPage: the Placar (brief T3.18) at the top of /lab", () => {
  it("shows the honest empty state when no version has emitted a signal yet", async () => {
    getLabSummaryMock.mockResolvedValue(exampleSummary());
    const jsx = await renderPage();
    render(jsx);
    expect(screen.getByText("Placar")).toBeInTheDocument();
    expect(screen.getByText("Nenhuma versão do Lab emitiu sinal ainda.")).toBeInTheDocument();
    expect(getLabScoreboardMock).toHaveBeenCalledWith({ as_of: expect.any(String) });
  });

  it("renders one card and one curve fetch per scoreboard row, freezing a single as_of for both", async () => {
    getLabSummaryMock.mockResolvedValue(exampleSummary());
    getLabScoreboardMock.mockResolvedValue({ as_of: "2026-09-08T12:00:00Z", label: "SOMBRA — hipotético, sem capital, custos assumidos", rows: [exampleScoreboardRow()] });

    const jsx = await renderPage();
    render(jsx);

    const card = screen.getByTestId("lab-scoreboard-card");
    expect(within(card).getByText("validada")).toBeInTheDocument();
    expect(getLabCurveMock).toHaveBeenCalledTimes(1);
    const scoreboardAsOf = (getLabScoreboardMock.mock.calls[0] as [{ as_of: string }])[0].as_of;
    expect(getLabCurveMock).toHaveBeenCalledWith({ version_id: exampleScoreboardRow().version.id, as_of: scoreboardAsOf });
  });

  it("degrades to an inline message, without failing the rest of the page, when the scoreboard fetch itself errors", async () => {
    getLabSummaryMock.mockResolvedValue(exampleSummary());
    getLabScoreboardMock.mockRejectedValue(new Error("network down"));

    const jsx = await renderPage();
    render(jsx);

    expect(screen.getByText(/Placar indisponível: falha ao carregar/)).toBeInTheDocument();
    // The rest of the page (the pre-existing Sombra tab) still renders.
    expect(screen.getByText("momentum / v2")).toBeInTheDocument();
  });

  it("never fabricates a curve line when the only version's own curve fetch fails -- the honest empty state, not a flat line", async () => {
    getLabSummaryMock.mockResolvedValue(exampleSummary());
    getLabScoreboardMock.mockResolvedValue({ as_of: "2026-09-08T12:00:00Z", label: "SOMBRA — hipotético, sem capital, custos assumidos", rows: [exampleScoreboardRow()] });
    getLabCurveMock.mockRejectedValue(new Error("timeout"));

    const jsx = await renderPage();
    render(jsx);

    expect(screen.getByText(/Nenhum resultado resolvido ainda para desenhar a curva/)).toBeInTheDocument();
  });
});

describe("LabPage: version <details> collapsed by default, opened by '?version=' (brief T3.24b item [4], Aceite)", () => {
  it("renders the version card's <details> closed when no ?version= is given", async () => {
    getLabSummaryMock.mockResolvedValue(exampleSummary());
    const jsx = await renderPage();
    render(jsx);
    const details = screen.getByText("momentum / v2").closest("details");
    expect((details as HTMLDetailsElement).open).toBe(false);
  });

  it("renders it open when ?version= matches this card's strategy_version_id", async () => {
    getLabSummaryMock.mockResolvedValue(exampleSummary());
    const jsx = await renderPage({ version: "098b060c-cdc0-46a6-b88b-70d4a5472b97" });
    render(jsx);
    const details = screen.getByText("momentum / v2").closest("details");
    expect((details as HTMLDetailsElement).open).toBe(true);
  });
});

describe("LabPage: DOM order (brief T3.24b §2, opção A -- Placar-primeiro, Aceite)", () => {
  it("renders lab-header before lab-scoreboard-section, before the signals grid ('Sinais do Shadow Lab')", async () => {
    getLabSummaryMock.mockResolvedValue(exampleSummary());
    getLabSignalsMock.mockResolvedValue({ items: [exampleSignal()], next_cursor: null, totals: exampleSignalsTotals({ closed: 1, open: 0, pending: 0, all: 1 }), page: exampleSignalsPageRange({ to: 1 }) });
    getLabScoreboardMock.mockResolvedValue({
      as_of: "2026-09-08T12:00:00Z",
      label: "SOMBRA — hipotético, sem capital, custos assumidos",
      rows: [exampleScoreboardRow()],
    });

    const jsx = await renderPage();
    const { container } = render(jsx);

    const header = screen.getByTestId("lab-header");
    const scoreboardSection = screen.getByTestId("lab-scoreboard-section");
    const signalsGrid = screen.getByRole("grid", { name: "Sinais do Shadow Lab" });

    // `Node.compareDocumentPosition` bit 4 (DOCUMENT_POSITION_FOLLOWING) means "b follows a".
    const headerBeforeScoreboard = header.compareDocumentPosition(scoreboardSection) & Node.DOCUMENT_POSITION_FOLLOWING;
    const scoreboardBeforeSignals = scoreboardSection.compareDocumentPosition(signalsGrid) & Node.DOCUMENT_POSITION_FOLLOWING;
    expect(headerBeforeScoreboard).toBeTruthy();
    expect(scoreboardBeforeSignals).toBeTruthy();
    expect(container).toBeInTheDocument();
  });
});

describe("LabPage: T3.37 contract -- state/page_size/cursor read from the URL, real totals passed down", () => {
  it("defaults to state=closed and page_size=200 when the URL has neither, with no cursor (page 1)", async () => {
    getLabSummaryMock.mockResolvedValue(exampleSummary());
    await renderPage();
    expect(getLabSignalsMock).toHaveBeenCalledWith(expect.objectContaining({ cohort: "prospective", state: "closed", page_size: 200 }));
    const [callArgs] = getLabSignalsMock.mock.calls[0] as [{ cursor?: string }];
    expect(callArgs.cursor).toBeUndefined();
  });

  it("reads state/page_size/cursor (the last of repeated '?c=') from the URL and forwards them to getLabSignals", async () => {
    getLabSummaryMock.mockResolvedValue(exampleSummary());
    await renderPage({ state: "open", page_size: "50" });
    expect(getLabSignalsMock).toHaveBeenCalledWith(expect.objectContaining({ state: "open", page_size: 50 }));
  });

  it("ignores an unrecognized state/page_size, falling back to the web's own default", async () => {
    getLabSummaryMock.mockResolvedValue(exampleSummary());
    await renderPage({ state: "bogus", page_size: "999" });
    expect(getLabSignalsMock).toHaveBeenCalledWith(expect.objectContaining({ state: "closed", page_size: 200 }));
  });

  it("shows the tabs' real totals (from the signals response), not a count of the loaded rows", async () => {
    getLabSummaryMock.mockResolvedValue(exampleSummary());
    getLabSignalsMock.mockResolvedValue({
      items: [exampleSignal()],
      next_cursor: null,
      totals: exampleSignalsTotals(),
      page: exampleSignalsPageRange({ to: 1 }),
    });
    const jsx = await renderPage();
    render(jsx);
    expect(screen.getByRole("tab", { name: "Concluídas (929)" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Todas (2.135)" })).toBeInTheDocument();
  });

  it("shows SectionUnavailable for just 'Sinais — Sombra' when the signals fetch fails, without failing the rest of the page", async () => {
    getLabSummaryMock.mockResolvedValue(exampleSummary());
    getLabSignalsMock.mockRejectedValue(new Error("network down"));
    const jsx = await renderPage();
    render(jsx);
    expect(screen.getByText(/Sinais — Sombra indisponível: falha ao carregar/)).toBeInTheDocument();
    // The rest of the page (header, version card) still renders.
    expect(screen.getByText("momentum / v2")).toBeInTheDocument();
    expect(screen.queryByText(/sem verificação/)).not.toBeInTheDocument();
  });
});
