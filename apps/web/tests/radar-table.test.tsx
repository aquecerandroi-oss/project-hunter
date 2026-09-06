import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@clerk/nextjs", () => ({
  useAuth: () => ({ getToken: async () => null }),
}));

const routerPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn(), push: routerPush }),
}));

const realtimeOnMessageRef = vi.hoisted<{ current: (() => void) | null }>(() => ({ current: null }));
vi.mock("@/hooks/useRealtime", () => ({
  useRealtime: (opts: { onMessage?: () => void }) => {
    realtimeOnMessageRef.current = opts.onMessage ?? null;
    return { status: "closed" };
  },
}));

const loadRadarActionMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api/radar-actions", () => ({ loadRadarAction: loadRadarActionMock }));
const loadRadarAnomaliesAggregateActionMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api/anomalies-actions", () => ({ loadRadarAnomaliesAggregateAction: loadRadarAnomaliesAggregateActionMock }));

afterEach(() => {
  cleanup();
  routerPush.mockClear();
  loadRadarActionMock.mockReset();
  loadRadarAnomaliesAggregateActionMock.mockReset();
});

import { RadarTable } from "@/components/radar/radar-table";
import type { AnomaliesAggregate } from "@/lib/api/anomalies-types";
import { makeRadarItem } from "@/tests/fixtures/radar";

const baseParams = { org_id: "org-1", sort: "score" as const, order: "desc" as const, limit: 200 };

function anomalies(overrides: Partial<AnomaliesAggregate> = {}): AnomaliesAggregate {
  return { byMarket: {}, unavailable: false, truncated: false, asOf: "2026-09-06T08:00:00Z", ...overrides };
}

describe("RadarTable: renders real rows from the T2.6 contract, no invented data", () => {
  it("shows symbol, score, status and stage chips for each row", () => {
    render(
      <RadarTable
        orgSlug="acme"
        initialItems={[makeRadarItem()]}
        initialCursor={null}
        initialAsOf="2026-09-06T08:00:00Z"
        hasFilters={false}
        baseParams={baseParams}
        initialAnomalies={anomalies()}
      />,
    );
    expect(screen.getByText("BTCUSDT")).toBeInTheDocument();
    expect(screen.getByText("55.00")).toBeInTheDocument();
    expect(screen.getByText("WATCHING")).toBeInTheDocument();
  });

  it("shows the EXTENDED status distinctly, never hidden behind a default color", () => {
    render(
      <RadarTable
        orgSlug="acme"
        initialItems={[makeRadarItem({ status: "EXTENDED", opportunity_id: "ext-1" })]}
        initialCursor={null}
        initialAsOf="2026-09-06T08:00:00Z"
        hasFilters={false}
        baseParams={baseParams}
        initialAnomalies={anomalies()}
      />,
    );
    expect(screen.getByText("EXTENDED")).toBeInTheDocument();
  });

  it("shows a real EARLY/DEVELOPING/EXTENDED stage chip, and 'estágio indisponível' (never a bare EARLY) for stage NONE", () => {
    render(
      <RadarTable
        orgSlug="acme"
        initialItems={[makeRadarItem({ stage: "NONE" })]}
        initialCursor={null}
        initialAsOf="2026-09-06T08:00:00Z"
        hasFilters={false}
        baseParams={baseParams}
        initialAnomalies={anomalies()}
      />,
    );
    expect(screen.getByText("estágio indisponível")).toBeInTheDocument();
  });
});

describe("RadarTable: the anomalies column is honestly scoped", () => {
  it("shows 'sem verificação' when the aggregate anomalies read failed, not a fabricated zero", () => {
    render(
      <RadarTable
        orgSlug="acme"
        initialItems={[makeRadarItem()]}
        initialCursor={null}
        initialAsOf="2026-09-06T08:00:00Z"
        hasFilters={false}
        baseParams={baseParams}
        initialAnomalies={anomalies({ unavailable: true })}
      />,
    );
    expect(screen.getByText("sem verificação")).toBeInTheDocument();
  });

  it("shows the real count and types once the aggregate succeeds", () => {
    render(
      <RadarTable
        orgSlug="acme"
        initialItems={[makeRadarItem()]}
        initialCursor={null}
        initialAsOf="2026-09-06T08:00:00Z"
        hasFilters={false}
        baseParams={baseParams}
        initialAnomalies={anomalies({ byMarket: { "22222222-2222-2222-2222-222222222222": [{ type: "VOLUME_SPIKE" }] } })}
      />,
    );
    expect(screen.getByText(/VOLUME_SPIKE/)).toBeInTheDocument();
  });

  it("still shows a truncation caveat for a market absent from a truncated aggregate, never a silent 'nenhuma'", () => {
    render(
      <RadarTable
        orgSlug="acme"
        initialItems={[makeRadarItem()]}
        initialCursor={null}
        initialAsOf="2026-09-06T08:00:00Z"
        hasFilters={false}
        baseParams={baseParams}
        initialAnomalies={anomalies({ truncated: true })}
      />,
    );
    expect(screen.getByText(/lista truncada/)).toBeInTheDocument();
  });
});

describe("RadarTable: honest empty states (distinct from a filtered miss)", () => {
  it("says no episode scored yet when there are no filters", () => {
    render(
      <RadarTable
        orgSlug="acme"
        initialItems={[]}
        initialCursor={null}
        initialAsOf="2026-09-06T08:00:00Z"
        hasFilters={false}
        baseParams={baseParams}
        initialAnomalies={anomalies()}
      />,
    );
    expect(screen.getByText(/Nenhuma oportunidade pontuada ainda/)).toBeInTheDocument();
  });

  it("says no episode matched the filters when filters are active", () => {
    render(
      <RadarTable
        orgSlug="acme"
        initialItems={[]}
        initialCursor={null}
        initialAsOf="2026-09-06T08:00:00Z"
        hasFilters
        baseParams={baseParams}
        initialAnomalies={anomalies()}
      />,
    );
    expect(screen.getByText(/Nenhum episódio encontrado para estes filtros/)).toBeInTheDocument();
  });
});

describe("RadarTable: cursor pagination via the Server Action", () => {
  it("appends the next page's rows and clears the cursor when it runs out", async () => {
    loadRadarActionMock.mockResolvedValue({
      ok: true,
      page: { items: [makeRadarItem({ opportunity_id: "opp-2", symbol: "ETHUSDT" })], next_cursor: null, as_of: "2026-09-06T08:05:00Z", org_scoped: true },
    });
    render(
      <RadarTable
        orgSlug="acme"
        initialItems={[makeRadarItem()]}
        initialCursor="cursor-1"
        initialAsOf="2026-09-06T08:00:00Z"
        hasFilters={false}
        baseParams={baseParams}
        initialAnomalies={anomalies()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Carregar mais" }));

    await waitFor(() => expect(screen.getByText("ETHUSDT")).toBeInTheDocument());
    expect(loadRadarActionMock).toHaveBeenCalledWith({ ...baseParams, cursor: "cursor-1" });
    expect(screen.getByRole("button", { name: "Fim da lista" })).toBeDisabled();
  });

  it("drops a load-more response superseded by a newer reconciliation, never mixing rows from two requests (Astra's T2.7 diff review, must-fix 1)", async () => {
    let resolveLoadMore!: (value: unknown) => void;
    loadRadarActionMock
      .mockImplementationOnce(() => new Promise((resolve) => (resolveLoadMore = resolve)))
      .mockResolvedValueOnce({
        ok: true,
        page: { items: [makeRadarItem({ opportunity_id: "opp-3", symbol: "SOLUSDT" })], next_cursor: null, as_of: "2026-09-06T08:06:00Z", org_scoped: true },
      });
    loadRadarAnomaliesAggregateActionMock.mockResolvedValue(anomalies());
    render(
      <RadarTable
        orgSlug="acme"
        initialItems={[makeRadarItem()]}
        initialCursor="cursor-1"
        initialAsOf="2026-09-06T08:00:00Z"
        hasFilters={false}
        baseParams={baseParams}
        initialAnomalies={anomalies()}
      />,
    );

    // Dispatch "load more" (in flight, unresolved) ...
    fireEvent.click(screen.getByRole("button", { name: "Carregar mais" }));
    // ... then a `rt:radar` message triggers a reconciliation (a newer
    // dispatch) while it is still pending, and that one resolves FIRST.
    await act(async () => {
      realtimeOnMessageRef.current?.();
    });
    await waitFor(() => expect(screen.getByText("SOLUSDT")).toBeInTheDocument());
    // The load-more's own response now arrives, but it was superseded --
    // applying it would mix ETHUSDT into a state built for a different
    // request (BTCUSDT would already be gone, replaced by SOLUSDT).
    await act(async () => {
      resolveLoadMore({
        ok: true,
        page: { items: [makeRadarItem({ opportunity_id: "opp-2", symbol: "ETHUSDT" })], next_cursor: "cursor-2", as_of: "2026-09-06T08:05:00Z", org_scoped: true },
      });
    });

    expect(screen.queryByText("ETHUSDT")).not.toBeInTheDocument();
    expect(screen.getByText("SOLUSDT")).toBeInTheDocument();
  });
});

describe("RadarTable: accessibility (grid roles, focus)", () => {
  it("exposes a grid with columnheaders and the real (unvirtualized) row count", () => {
    render(
      <RadarTable
        orgSlug="acme"
        initialItems={[makeRadarItem()]}
        initialCursor={null}
        initialAsOf="2026-09-06T08:00:00Z"
        hasFilters={false}
        baseParams={baseParams}
        initialAnomalies={anomalies()}
      />,
    );
    const grid = screen.getByRole("grid", { name: "Radar de oportunidades" });
    expect(grid).toHaveAttribute("aria-rowcount", "2");
    expect(screen.getByRole("columnheader", { name: /Score/ })).toBeInTheDocument();
  });

  it("moves the row selection with arrow keys and opens the detail on Enter", () => {
    render(
      <RadarTable
        orgSlug="acme"
        initialItems={[makeRadarItem()]}
        initialCursor={null}
        initialAsOf="2026-09-06T08:00:00Z"
        hasFilters={false}
        baseParams={baseParams}
        initialAnomalies={anomalies()}
      />,
    );
    const grid = screen.getByRole("grid", { name: "Radar de oportunidades" });
    fireEvent.keyDown(grid, { key: "ArrowDown" });
    fireEvent.keyDown(grid, { key: "Enter" });
    expect(routerPush).toHaveBeenCalledWith("/acme/opportunities/11111111-1111-1111-1111-111111111111");
  });
});
