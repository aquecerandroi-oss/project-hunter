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

/**
 * `LabTotalsCard`'s own unit coverage lives in `lab-signals-table.test.tsx`'s
 * sibling file `lab-totals-card.test.tsx`? No -- this file exercises it
 * mounted *inside* `LabSignalsTable` (the real integration point, `rows`
 * always the currently loaded items, never a second fetch). Split out of
 * `lab-signals-table.test.tsx` to keep that file under the lint config's
 * 350-line budget (brief T3.24b grew its own totals-card coverage).
 */
describe("LabSignalsTable: the totals card (brief T3.17 item 2, extended by T3.17b item 1, compacted by T3.24b item [3])", () => {
  it("shows 4 compact stats by default, computed from the loaded rows -- never scoped to the currently selected segment", () => {
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
    expect(within(card).getByText("Operações")).toBeInTheDocument();
    expect(within(card).getByText("3")).toBeInTheDocument(); // total
    expect(within(card).getByText("Com lucro / prejuízo")).toBeInTheDocument();
    expect(within(card).getByText("Taxa de acerto")).toBeInTheDocument();
    expect(within(card).getByText("Resultado acumulado")).toBeInTheDocument();
    // The other 8 stats stay hidden until "Mais detalhes" is opened.
    expect(within(card).queryByText("Melhor operação (desta página)")).not.toBeInTheDocument();

    fireEvent.click(within(card).getByRole("button", { name: "Mais detalhes" }));
    // Aceite (brief T3.24b): "Mais detalhes" opens exactly the other 8 stats.
    const moreLabels = [
      "Concluídas",
      "Pendentes",
      "Sem entrada",
      "Censuradas",
      "Média com lucro (desta página)",
      "Média com prejuízo (desta página)",
      "Melhor operação (desta página)",
      "Pior operação (desta página)",
    ];
    for (const label of moreLabels) expect(within(card).getByText(label)).toBeInTheDocument();
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
