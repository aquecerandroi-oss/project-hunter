import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { loadLabSignalsActionMock, resolveMarketHrefActionMock } = vi.hoisted(() => ({
  loadLabSignalsActionMock: vi.fn(),
  resolveMarketHrefActionMock: vi.fn(),
}));

vi.mock("@/lib/api/lab-actions", () => ({
  loadLabSignalsAction: loadLabSignalsActionMock,
  loadLabSignalEnvelopeAction: vi.fn(),
  resolveMarketHrefAction: resolveMarketHrefActionMock,
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

afterEach(cleanup);

import { LabSignalsTable } from "@/components/lab/lab-signals-table";
import { exampleRuler, makeSignal } from "@/tests/fixtures/lab";

const versionLabelById = { "098b060c-cdc0-46a6-b88b-70d4a5472b97": "momentum/v2" };

beforeEach(() => {
  loadLabSignalsActionMock.mockReset();
  resolveMarketHrefActionMock.mockReset().mockResolvedValue("/acme/markets/binance/AAAAUSDT");
});

describe("LabSignalsTable: honest empty state", () => {
  it("renders '0 sinais' as a result, not an error, when there are no items", () => {
    render(
      <LabSignalsTable
        orgSlug="acme"
        initialItems={[]}
        initialCursor={null}
        baseParams={{ cohort: "prospective" }}
        versionLabelById={versionLabelById}
        cohort="prospective"
        ruler={exampleRuler()}
      />,
    );
    expect(screen.getByText("0 sinais nesta seleção.")).toBeInTheDocument();
  });
});

describe("LabSignalsTable: 'Saiu' column states plain-language reasons (brief T3.17), chips move behind 'Detalhes de pesquisa'", () => {
  it("the default view shows 'não entrou: <motivo>' in the 'Saiu' column for a no_entry row (under the 'Pendentes/sem entrada' segment), and the chip only appears behind the research toggle", () => {
    const row = makeSignal({
      tracking_state: "no_entry",
      no_entry_reason: "late:delay",
      result: "invalidated",
      virtual_entry: null,
      entry_ts: null,
      exit_price: null,
      exit_ts: null,
    });
    render(
      <LabSignalsTable
        orgSlug="acme"
        initialItems={[row]}
        initialCursor={null}
        baseParams={{ cohort: "prospective" }}
        versionLabelById={versionLabelById}
        cohort="prospective"
        ruler={exampleRuler()}
      />,
    );
    // Default segment is "Concluídas" (brief T3.17b item 4) -- a no_entry row
    // only shows up under "Pendentes/sem entrada".
    fireEvent.click(screen.getByRole("tab", { name: /Pendentes\/sem entrada/ }));
    expect(screen.getByText(/não entrou:/)).toBeInTheDocument();
    expect(screen.queryByText(/sem entrada:/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Detalhes de pesquisa" }));
    expect(screen.getByText(/sem entrada:/)).toBeInTheDocument();
  });

  it("the default view shows 'censurada: <motivo>' in the 'Saiu' column for a censored row (under the 'Pendentes/sem entrada' segment), and the chip only appears behind the research toggle", () => {
    const row = makeSignal({ tracking_state: "censored", censored_reason: "gap:failed", result: "expired", exit_price: null, exit_ts: null });
    render(
      <LabSignalsTable
        orgSlug="acme"
        initialItems={[row]}
        initialCursor={null}
        baseParams={{ cohort: "prospective" }}
        versionLabelById={versionLabelById}
        cohort="prospective"
        ruler={exampleRuler()}
      />,
    );
    fireEvent.click(screen.getByRole("tab", { name: /Pendentes\/sem entrada/ }));
    expect(screen.getByText(/censurada:/)).toBeInTheDocument();
    expect(screen.queryByText(/^censurado:/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Detalhes de pesquisa" }));
    expect(screen.getByText(/^censurado:/)).toBeInTheDocument();
  });

  it("never colors r_multiple's reason text as if it were a number", () => {
    const row = makeSignal({ r_multiple: null, r_multiple_reason: "no_sample" });
    render(
      <LabSignalsTable
        orgSlug="acme"
        initialItems={[row]}
        initialCursor={null}
        baseParams={{ cohort: "prospective" }}
        versionLabelById={versionLabelById}
        cohort="prospective"
        ruler={exampleRuler()}
      />,
    );
    const cell = screen.getByText(/sem amostra madura/);
    expect(cell.className).toContain("text-fg-muted");
    expect(cell.className).not.toContain("text-green");
    expect(cell.className).not.toContain("text-red");
  });
});

describe("LabSignalsTable: ARIA grid role tree", () => {
  it("exposes role=grid, one row per item plus the header, and gridcells", () => {
    const rows = [makeSignal(), makeSignal({ signal_id: "second-id", market: "BBBBUSDT" })];
    render(
      <LabSignalsTable
        orgSlug="acme"
        initialItems={rows}
        initialCursor={null}
        baseParams={{ cohort: "prospective" }}
        versionLabelById={versionLabelById}
        cohort="prospective"
        ruler={exampleRuler()}
      />,
    );
    expect(screen.getByRole("grid", { name: "Sinais do Shadow Lab" })).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(3); // header + 2 data rows
    const dataRow = screen.getByText("AAAAUSDT").closest('[role="row"]');
    expect(dataRow).not.toBeNull();
    expect(within(dataRow as HTMLElement).getAllByRole("gridcell").length).toBeGreaterThan(0);
  });
});

describe("LabSignalsTable: cursor pagination via a Server Action", () => {
  it("appends the next page's items and advances the cursor on 'Carregar mais'", async () => {
    loadLabSignalsActionMock.mockResolvedValue({
      ok: true,
      page: { items: [makeSignal({ signal_id: "page-2-id", market: "CCCCUSDT" })], next_cursor: null },
    });
    render(
      <LabSignalsTable
        orgSlug="acme"
        initialItems={[makeSignal()]}
        initialCursor="cursor-1"
        baseParams={{ cohort: "prospective" }}
        versionLabelById={versionLabelById}
        cohort="prospective"
        ruler={exampleRuler()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Carregar mais" }));

    expect(await screen.findByText("CCCCUSDT")).toBeInTheDocument();
    expect(loadLabSignalsActionMock).toHaveBeenCalledWith({ cohort: "prospective", cursor: "cursor-1" });
    // The next page reported `next_cursor: null` -- the button must reflect
    // there being no further page, never keep inviting another click.
    expect(await screen.findByRole("button", { name: "Fim da lista" })).toBeDisabled();
  });

  it("shows the load error and keeps the existing items when the action fails", async () => {
    loadLabSignalsActionMock.mockResolvedValue({ ok: false, page: { items: [], next_cursor: null }, reason: "Shadow Lab indisponível" });
    render(
      <LabSignalsTable
        orgSlug="acme"
        initialItems={[makeSignal()]}
        initialCursor="cursor-1"
        baseParams={{ cohort: "prospective" }}
        versionLabelById={versionLabelById}
        cohort="prospective"
        ruler={exampleRuler()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Carregar mais" }));

    expect(await screen.findByText("Shadow Lab indisponível")).toBeInTheDocument();
    expect(screen.getByText("AAAAUSDT")).toBeInTheDocument();
  });
});

describe("LabSignalsTable: the endpoint's own window scope is a tooltip, not a paragraph leaking into the UI (brief T3.17b item 2)", () => {
  it("shows the short 'período: todo o disponível' label, with the full technical fact only in its title tooltip", () => {
    render(
      <LabSignalsTable
        orgSlug="acme"
        initialItems={[makeSignal()]}
        initialCursor={null}
        baseParams={{ cohort: "prospective" }}
        versionLabelById={versionLabelById}
        cohort="prospective"
        ruler={exampleRuler()}
      />,
    );
    const label = screen.getByText("período: todo o disponível");
    expect(label).toBeInTheDocument();
    expect(label.title).toMatch(/não aceita janela\/as_of/);
    // The old paragraph -- "Sinais · todo o período disponível (este endpoint
    // não aceita janela/`as_of`..." -- must not leak into the visible UI.
    expect(screen.queryByText(/este endpoint não aceita/)).not.toBeInTheDocument();
  });
});

describe("LabSignalsTable: the totals card (brief T3.17 item 2, extended by T3.17b item 1)", () => {
  it("shows the plain-money totals above the table, computed from the loaded rows -- never scoped to the currently selected segment", () => {
    const rows = [
      makeSignal({ signal_id: "1", tracking_state: "terminal", r_multiple: "1.0" }),
      makeSignal({ signal_id: "2", tracking_state: "terminal", r_multiple: "-0.5" }),
      makeSignal({ signal_id: "3", tracking_state: "pending_entry", r_multiple: null, r_multiple_reason: null }),
    ];
    render(
      <LabSignalsTable
        orgSlug="acme"
        initialItems={rows}
        initialCursor={null}
        baseParams={{ cohort: "prospective" }}
        versionLabelById={versionLabelById}
        cohort="prospective"
        ruler={exampleRuler()}
      />,
    );
    const card = screen.getByTestId("lab-totals-card");
    expect(within(card).getByText("Operações simuladas")).toBeInTheDocument();
    expect(within(card).getByText("3")).toBeInTheDocument(); // total
    expect(within(card).getByText("Resultado acumulado (USDT)")).toBeInTheDocument();
    expect(within(card).getByText("Resultado acumulado (BRL)")).toBeInTheDocument();
    expect(within(card).getByText("Melhor operação (desta página)")).toBeInTheDocument();
    expect(within(card).getByText("Pior operação (desta página)")).toBeInTheDocument();
  });

  it("says 'desta página' with the loaded count when a next page exists, and never the old 'há mais sinais além desta página' phrasing", () => {
    const { unmount } = render(
      <LabSignalsTable
        orgSlug="acme"
        initialItems={[makeSignal()]}
        initialCursor={null}
        baseParams={{ cohort: "prospective" }}
        versionLabelById={versionLabelById}
        cohort="prospective"
        ruler={exampleRuler()}
      />,
    );
    expect(screen.getByText("Resultado de todas as operações do período (1)")).toBeInTheDocument();
    expect(screen.queryByText(/há mais sinais/)).not.toBeInTheDocument();
    unmount();

    render(
      <LabSignalsTable
        orgSlug="acme"
        initialItems={[makeSignal()]}
        initialCursor="cursor-1"
        baseParams={{ cohort: "prospective" }}
        versionLabelById={versionLabelById}
        cohort="prospective"
        ruler={exampleRuler()}
      />,
    );
    expect(screen.getByText("Resultado das operações desta página (1)")).toBeInTheDocument();
    // T3.24a: `LAB_TOTALS_SCOPE_NOTE` (a stale task-id-bearing note) was
    // removed from `lab-totals-card.tsx` -- the Placar is on the same page
    // and the heading above already scopes the number, so no note is shown.
    expect(screen.queryByText(/os totais do Lab inteiro/)).not.toBeInTheDocument();
    expect(screen.queryByText(/T3\.18/)).not.toBeInTheDocument();
    expect(screen.queryByText(/há mais sinais/)).not.toBeInTheDocument();
  });
});

describe("LabSignalsTable: segments (brief T3.17b item 4)", () => {
  it("defaults to 'Concluídas' -- a terminal row shows, a pending row does not, until the tab changes", () => {
    const rows = [
      makeSignal({ signal_id: "done", market: "AAAAUSDT", tracking_state: "terminal" }),
      makeSignal({ signal_id: "pending", market: "BBBBUSDT", tracking_state: "pending_entry" }),
    ];
    render(
      <LabSignalsTable
        orgSlug="acme"
        initialItems={rows}
        initialCursor={null}
        baseParams={{ cohort: "prospective" }}
        versionLabelById={versionLabelById}
        cohort="prospective"
        ruler={exampleRuler()}
      />,
    );
    expect(screen.getByRole("tab", { name: /Concluídas/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("AAAAUSDT")).toBeInTheDocument();
    expect(screen.queryByText("BBBBUSDT")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: /Todas/ }));
    expect(screen.getByText("AAAAUSDT")).toBeInTheDocument();
    expect(screen.getByText("BBBBUSDT")).toBeInTheDocument();
  });

  it("shows a count next to each segment label, based on every loaded row", () => {
    const rows = [
      makeSignal({ signal_id: "1", tracking_state: "terminal" }),
      makeSignal({ signal_id: "2", tracking_state: "terminal" }),
      makeSignal({ signal_id: "3", tracking_state: "active" }),
      makeSignal({ signal_id: "4", tracking_state: "no_entry" }),
    ];
    render(
      <LabSignalsTable
        orgSlug="acme"
        initialItems={rows}
        initialCursor={null}
        baseParams={{ cohort: "prospective" }}
        versionLabelById={versionLabelById}
        cohort="prospective"
        ruler={exampleRuler()}
      />,
    );
    expect(screen.getByRole("tab", { name: "Concluídas (2)" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Abertas (1)" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Pendentes/sem entrada (1)" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Todas (4)" })).toBeInTheDocument();
  });

  it("shows its own honest empty state (never the whole-table empty state) when a segment has no rows", () => {
    const rows = [makeSignal({ tracking_state: "pending_entry" })];
    render(
      <LabSignalsTable
        orgSlug="acme"
        initialItems={rows}
        initialCursor={null}
        baseParams={{ cohort: "prospective" }}
        versionLabelById={versionLabelById}
        cohort="prospective"
        ruler={exampleRuler()}
      />,
    );
    // Default "Concluídas" is empty here (the only row is pending_entry).
    expect(screen.getByText(/Nenhum sinal em "Concluídas" nesta seleção/)).toBeInTheDocument();
  });
});
