import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { resolveMarketHrefActionMock } = vi.hoisted(() => ({
  resolveMarketHrefActionMock: vi.fn(),
}));

vi.mock("@/lib/api/lab-actions", () => ({
  loadLabSignalEnvelopeAction: vi.fn(),
  resolveMarketHrefAction: resolveMarketHrefActionMock,
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

afterEach(cleanup);

import { LabSignalsTable } from "@/components/lab/lab-signals-table";
import { makeSignal, makeVersionSummary } from "@/tests/fixtures/lab";
import { exampleLabSignalsTableProps } from "@/tests/fixtures/lab-pagination";

beforeEach(() => {
  resolveMarketHrefActionMock.mockReset().mockResolvedValue("/acme/markets/binance/AAAAUSDT");
});

/**
 * `LabTotalsCard`'s own unit coverage lives in `tests/lab-money.test.ts`
 * (pure math) -- this file exercises it mounted *inside* `LabSignalsTable`
 * (the real integration point, `rows` always the currently loaded items,
 * never a second fetch). Split out of `lab-signals-table.test.tsx` to keep
 * that file under the lint config's 350-line budget.
 */
describe("LabSignalsTable: the totals card (brief T3.17 item 2, extended by T3.17b item 1, compacted by T3.24b item [3])", () => {
  it("shows 4 compact stats by default, computed from the loaded page's own rows -- never scoped to the currently selected segment", () => {
    const rows = [
      makeSignal({ signal_id: "1", tracking_state: "terminal", r_multiple: "1.0" }),
      makeSignal({ signal_id: "2", tracking_state: "terminal", r_multiple: "-0.5" }),
      makeSignal({ signal_id: "3", tracking_state: "pending_entry", r_multiple: null, r_multiple_reason: null }),
    ];
    render(<LabSignalsTable {...exampleLabSignalsTableProps({ items: rows, state: "all", totals: { closed: 2, open: 0, pending: 1, all: 3 } })} />);
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

  it("says 'desta página' with the loaded page's own count, in the default 'page' scope", () => {
    render(<LabSignalsTable {...exampleLabSignalsTableProps({ items: [makeSignal()] })} />);
    expect(screen.getByText("Resultado das operações desta página (1)")).toBeInTheDocument();
    expect(screen.queryByText(/há mais sinais/)).not.toBeInTheDocument();
    expect(screen.queryByText(/T3\.18/)).not.toBeInTheDocument();
  });
});

/**
 * Brief T3.37's explicit scope switch: "desta página" | "de todas as
 * concluídas", the second backed by `GET /lab/shadow/summary` (already
 * fetched by the page and passed down here), never a client sum of a page.
 */
describe("LabSignalsTable: the totals card's scope switch (brief T3.37)", () => {
  it("switches the heading and the 'Operações' count to the real, whole-dataset closed total when 'De todas as concluídas' is clicked", () => {
    render(
      <LabSignalsTable
        {...exampleLabSignalsTableProps({
          items: [makeSignal()],
          totals: { closed: 929, open: 0, pending: 0, all: 929 },
        })}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "De todas as concluídas" }));
    expect(screen.getByText("Resultado de todas as operações concluídas (929)")).toBeInTheDocument();
    expect(screen.getByText("929")).toBeInTheDocument();
  });

  it("computes the whole-dataset money from the version summary's sum_of_hypothetical_r (never a client sum of the page's own rows)", () => {
    const summary = {
      as_of: "2026-09-06T12:00:00Z",
      window: "all",
      cohort: "prospective",
      label: "SOMBRA — hipotético, sem capital, custos assumidos",
      versions: [
        makeVersionSummary({
          strategy_version_id: "v1",
          metrics: { ...makeVersionSummary().metrics, sum_of_hypothetical_r: { value: "10", reason: null, count: 40, ordered_by: "exit_ts" } },
        }),
      ],
    };
    render(
      <LabSignalsTable
        {...exampleLabSignalsTableProps({
          items: [makeSignal({ r_multiple: "999" })], // a huge page-scoped value that must NOT leak into the allClosed scope
          summary,
          versionId: "v1",
        })}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "De todas as concluídas" }));
    // ruler's riskUsdt from `exampleRuler()` is 19.333,01 * 0,25% = 48,332525
    // USDT; sum_of_hypothetical_r "10" * riskUsdt = 483,33 USDT -- never a
    // number derived from the page's own r_multiple "999".
    expect(screen.getByText("+483.33 USDT")).toBeInTheDocument();
  });
});
