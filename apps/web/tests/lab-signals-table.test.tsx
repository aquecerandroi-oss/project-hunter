import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { resolveMarketHrefActionMock, pushMock } = vi.hoisted(() => ({
  resolveMarketHrefActionMock: vi.fn(),
  pushMock: vi.fn(),
}));

vi.mock("@/lib/api/lab-actions", () => ({
  loadLabSignalEnvelopeAction: vi.fn(),
  resolveMarketHrefAction: resolveMarketHrefActionMock,
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, refresh: vi.fn() }),
}));

afterEach(cleanup);

import { LabSignalsTable } from "@/components/lab/lab-signals-table";
import { makeSignal } from "@/tests/fixtures/lab";
import { exampleLabSignalsTableProps } from "@/tests/fixtures/lab-pagination";

beforeEach(() => {
  pushMock.mockReset();
  resolveMarketHrefActionMock.mockReset().mockResolvedValue("/acme/markets/binance/AAAAUSDT");
});

describe("LabSignalsTable: honest empty state", () => {
  it("renders '0 sinais' as a result, not an error, when totals.all is 0", () => {
    render(<LabSignalsTable {...exampleLabSignalsTableProps({ items: [], totals: { closed: 0, open: 0, pending: 0, all: 0 } })} />);
    expect(screen.getByText("0 sinais nesta seleção.")).toBeInTheDocument();
  });
});

describe("LabSignalsTable: 'Saiu' column states plain-language reasons (brief T3.17), chips move behind 'Detalhes de pesquisa'", () => {
  it("the default view shows 'não entrou: <motivo>' in the 'Saiu' column, the chip only appears behind the research toggle", () => {
    const row = makeSignal({
      tracking_state: "no_entry",
      no_entry_reason: "late:delay",
      result: "invalidated",
      virtual_entry: null,
      entry_ts: null,
      exit_price: null,
      exit_ts: null,
    });
    render(<LabSignalsTable {...exampleLabSignalsTableProps({ items: [row], state: "pending" })} />);
    expect(screen.getByText(/não entrou:/)).toBeInTheDocument();
    expect(screen.queryByText(/sem entrada:/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Detalhes de pesquisa" }));
    expect(screen.getByText(/sem entrada:/)).toBeInTheDocument();
  });

  it("never colors r_multiple's reason text as if it were a number", () => {
    const row = makeSignal({ r_multiple: null, r_multiple_reason: "no_sample" });
    render(<LabSignalsTable {...exampleLabSignalsTableProps({ items: [row] })} />);
    const cell = screen.getByText(/sem amostra madura/);
    expect(cell.className).toContain("text-fg-muted");
    expect(cell.className).not.toContain("text-green");
    expect(cell.className).not.toContain("text-red");
  });
});

describe("LabSignalsTable: ARIA grid role tree", () => {
  it("exposes role=grid, one row per item plus the header, and gridcells", () => {
    const rows = [makeSignal(), makeSignal({ signal_id: "second-id", market: "BBBBUSDT" })];
    render(<LabSignalsTable {...exampleLabSignalsTableProps({ items: rows })} />);
    expect(screen.getByRole("grid", { name: "Sinais do Shadow Lab" })).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(3); // header + 2 data rows
    const dataRow = screen.getByText("AAAAUSDT").closest('[role="row"]');
    expect(dataRow).not.toBeNull();
    expect(within(dataRow as HTMLElement).getAllByRole("gridcell").length).toBeGreaterThan(0);
  });
});

describe("LabSignalsTable: the endpoint's own window scope is now a visible note, not a tooltip (brief T3.24b item [3])", () => {
  it("shows 'período: todo o disponível — a janela acima só filtra o resumo' as plain visible text", () => {
    render(<LabSignalsTable {...exampleLabSignalsTableProps()} />);
    expect(screen.getByText("período: todo o disponível — a janela acima só filtra o resumo")).toBeInTheDocument();
  });
});

describe("LabSignalsTable: the money-tooltip fact is one visible footer note, never a per-cell title (brief T3.24b Aceite)", () => {
  it("shows the note exactly once and no gridcell carries the old MONEY_TOOLTIP text in its title", () => {
    render(<LabSignalsTable {...exampleLabSignalsTableProps()} />);
    expect(screen.getAllByText("Valores simulados: dado real, custos assumidos, sem dinheiro.")).toHaveLength(1);
    for (const cell of screen.getAllByRole("gridcell")) {
      expect(cell.title).not.toMatch(/simulado — dado real/);
    }
  });
});

describe("LabSignalsTable: segments show real totals and never filter the loaded page client-side (brief T3.37)", () => {
  it("renders exactly the rows the server sent, with no client-side re-filtering by tracking_state", () => {
    // Two rows in a mixed shape -- if the table still filtered client-side by
    // segment, the "open" one would vanish under the default "closed" tab.
    const rows = [
      makeSignal({ signal_id: "done", market: "AAAAUSDT", tracking_state: "terminal" }),
      makeSignal({ signal_id: "open-one", market: "BBBBUSDT", tracking_state: "active" }),
    ];
    render(<LabSignalsTable {...exampleLabSignalsTableProps({ items: rows, state: "closed" })} />);
    expect(screen.getByText("AAAAUSDT")).toBeInTheDocument();
    expect(screen.getByText("BBBBUSDT")).toBeInTheDocument();
  });

  it("shows the tabs' real totals from the totals prop, not a count of the loaded rows", () => {
    render(
      <LabSignalsTable
        {...exampleLabSignalsTableProps({ items: [makeSignal()], totals: { closed: 929, open: 340, pending: 866, all: 2135 } })}
      />,
    );
    expect(screen.getByRole("tab", { name: "Concluídas (929)" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Todas (2.135)" })).toBeInTheDocument();
  });

  // T3.51 (Everton on the VPS: "eu clico e não resolve nada"): the tab is a
  // real `<a href>` (`LabSegmentTabs`, `<Link>`) built from `buildLabHref`,
  // not a `<button onClick={() => router.push(...)}>` -- the assertion is
  // the anchor's own `href`, never a `router.push` call.
  it("renders a tab's own ?state= href built by buildLabHref, instead of filtering in place", () => {
    render(<LabSignalsTable {...exampleLabSignalsTableProps({ state: "closed" })} />);
    expect(screen.getByRole("tab", { name: /Abertas/ })).toHaveAttribute("href", expect.stringContaining("state=open"));
  });

  it("shows its own honest per-segment empty state when the current state's page is empty but totals.all is not 0", () => {
    render(<LabSignalsTable {...exampleLabSignalsTableProps({ items: [], state: "open", totals: { closed: 5, open: 0, pending: 1, all: 6 } })} />);
    expect(screen.getByText(/Nenhum sinal em "Abertas" nesta seleção/)).toBeInTheDocument();
  });
});

describe("LabSignalsTable: the pager prints the real 'X–Y de Z' range (brief T3.37)", () => {
  it("shows the page's own 1-based range against the current state's real total", () => {
    render(
      <LabSignalsTable
        {...exampleLabSignalsTableProps({
          page: { from: 1, to: 1 },
          totals: { closed: 929, open: 0, pending: 0, all: 929 },
        })}
      />,
    );
    expect(screen.getByText("1–1 de 929 · página 1")).toBeInTheDocument();
  });
});
