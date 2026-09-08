import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { loadLabSignalsActionMock, loadLabSignalEnvelopeActionMock, resolveMarketHrefActionMock } = vi.hoisted(() => ({
  loadLabSignalsActionMock: vi.fn(),
  loadLabSignalEnvelopeActionMock: vi.fn(),
  resolveMarketHrefActionMock: vi.fn(),
}));

vi.mock("@/lib/api/lab-actions", () => ({
  loadLabSignalsAction: loadLabSignalsActionMock,
  loadLabSignalEnvelopeAction: loadLabSignalEnvelopeActionMock,
  resolveMarketHrefAction: resolveMarketHrefActionMock,
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

afterEach(cleanup);

import { LabSignalPanel } from "@/components/lab/lab-signal-panel";
import { LabSignalsTable } from "@/components/lab/lab-signals-table";
import { exampleRuler, exampleSignal, makeSignal } from "@/tests/fixtures/lab";
import { exampleLabSignalsTableProps } from "@/tests/fixtures/lab-pagination";

beforeEach(() => {
  loadLabSignalsActionMock.mockReset();
  loadLabSignalEnvelopeActionMock.mockReset();
  resolveMarketHrefActionMock.mockReset().mockResolvedValue("/acme/markets/binance/AAAAUSDT");
});

/**
 * Nothing exercised `LabSignalPanel`/`LabSignalDetail`/`LabExcursions` before
 * this file -- the table only ever rendered rows, never opened the side
 * panel a click/Enter is supposed to fill in (code-reviewer must-fix #3).
 */
describe("LabSignalsTable -> LabSignalPanel: selecting a row (click) fills in the side panel", () => {
  it("shows the idle placeholder before any row is selected, then the selected signal's detail after a click", () => {
    render(<LabSignalsTable {...exampleLabSignalsTableProps({ items: [exampleSignal()] })} />);

    expect(screen.getByText(/Selecione um sinal na tabela/)).toBeInTheDocument();

    fireEvent.click(screen.getByText("AAAAUSDT").closest('[role="row"]') as HTMLElement);

    expect(screen.queryByText(/Selecione um sinal na tabela/)).not.toBeInTheDocument();
    // Panel-only content (the table row never shows a "Decisão:" label).
    expect(screen.getByText(/Decisão:/)).toBeInTheDocument();
  });

  it("also opens the panel on Enter (keyboard row navigation, hooks/useArrowKeyRowSelection)", () => {
    render(<LabSignalsTable {...exampleLabSignalsTableProps({ items: [exampleSignal()] })} />);

    const grid = screen.getByRole("grid", { name: "Sinais do Shadow Lab" });
    fireEvent.keyDown(grid, { key: "ArrowDown" });
    fireEvent.keyDown(grid, { key: "Enter" });

    expect(screen.queryByText(/Selecione um sinal na tabela/)).not.toBeInTheDocument();
    expect(screen.getByText(/Decisão:/)).toBeInTheDocument();
  });
});

describe("LabSignalPanel -> LabExcursions: mfe honesty (null+bounds vs. a known value)", () => {
  it("renders 'indeterminado' with the bounds and the 'ambíguo' badge when mfe is null and ambiguous is true", () => {
    // `exampleSignal()`'s excursions: mfe null, bounds.mfe [0, 4.2], ambiguous true.
    render(<LabSignalPanel signal={exampleSignal()} versionLabel="momentum/v2" ruler={exampleRuler()} />);

    const mfeRow = screen.getByText("MFE (favorável)").closest("div") as HTMLElement;
    expect(within(mfeRow).getByText(/indeterminado/)).toBeInTheDocument();
    expect(within(mfeRow).getByText(/\[0, 4\.2\]/)).toBeInTheDocument();
    // The mutation to kill: `known ?? "0"` would print a bare "0" here instead.
    expect(within(mfeRow).queryByText("0")).not.toBeInTheDocument();
    expect(screen.getByText("ambíguo")).toBeInTheDocument();
  });

  it("renders the real value (never '0') when mfe is a known Decimal string, without the ambíguo badge", () => {
    const signal = makeSignal({
      excursions: {
        ...exampleSignal().excursions,
        mfe: "1.2500",
        ambiguous: false,
      },
    });
    render(<LabSignalPanel signal={signal} versionLabel="momentum/v2" ruler={exampleRuler()} />);

    const mfeRow = screen.getByText("MFE (favorável)").closest("div") as HTMLElement;
    expect(within(mfeRow).getByText(/1\.2500 price/)).toBeInTheDocument();
    expect(within(mfeRow).queryByText(/indeterminado/)).not.toBeInTheDocument();
    expect(screen.queryByText("ambíguo")).not.toBeInTheDocument();
  });
});

describe("LabSignalPanel: sibling-version signals list (brief T3.38 item 1's 'or the side panel' option)", () => {
  it("lists every sibling's own version chip and signal_id when the group spans more than one version", () => {
    const [v4, v2, v3] = [
      makeSignal({ signal_id: "sig-v4", strategy_version_id: "v4-id", purpose: "research_only" }),
      makeSignal({ signal_id: "sig-v2", strategy_version_id: "v2-id", purpose: "research_only" }),
      makeSignal({ signal_id: "sig-v3", strategy_version_id: "v3-id", purpose: "paper" }),
    ];
    const versionLabelFor = (id: string) => ({ "v4-id": "momentum/v4", "v2-id": "momentum/v2", "v3-id": "momentum/v3" })[id] ?? id;
    render(
      <LabSignalPanel
        signal={v4}
        versionLabel="momentum/v4"
        ruler={exampleRuler()}
        siblingSignals={[v4, v2, v3]}
        versionLabelFor={versionLabelFor}
      />,
    );
    expect(screen.getByText("sig-v4")).toBeInTheDocument();
    expect(screen.getByText("sig-v2")).toBeInTheDocument();
    expect(screen.getByText("sig-v3")).toBeInTheDocument();
    expect(screen.getByText("momentum/v3")).toBeInTheDocument();
    expect(screen.getByText(/3 versões irmãs decidiram/)).toBeInTheDocument();
  });

  it("shows no sibling block for an ordinary, single-signal group", () => {
    render(
      <LabSignalPanel
        signal={exampleSignal()}
        versionLabel="momentum/v2"
        ruler={exampleRuler()}
        siblingSignals={[exampleSignal()]}
        versionLabelFor={(id) => id}
      />,
    );
    expect(screen.queryByText(/versões irmãs decidiram/)).not.toBeInTheDocument();
  });
});

/** Finding 2 of the T3.38 review: the panel's own money block never hides a sibling group whose members disagree on money -- shows the real range instead of `signal`'s (the group's primary) own value alone. */
describe("LabSignalPanel -> SignalMoneyBlock: divergent siblings show a range, never the primary's value alone (finding 2)", () => {
  it("shows 'Resultado' as a range with '(faixa)' when siblingSignals disagree on r_multiple", () => {
    const primary = makeSignal({ signal_id: "sig-a", r_multiple: "1.0" });
    const sibling = makeSignal({ signal_id: "sig-b", r_multiple: "2.0" });
    render(
      <LabSignalPanel
        signal={primary}
        versionLabel="momentum/v2"
        ruler={exampleRuler()}
        siblingSignals={[primary, sibling]}
        versionLabelFor={(id) => id}
      />,
    );
    expect(screen.getByText(/\(faixa\)/)).toBeInTheDocument();
  });

  it("shows the ordinary single value (no '(faixa)') when siblings agree", () => {
    const primary = makeSignal({ signal_id: "sig-a", r_multiple: "1.0" });
    const sibling = makeSignal({ signal_id: "sig-b", r_multiple: "1.0" });
    render(
      <LabSignalPanel
        signal={primary}
        versionLabel="momentum/v2"
        ruler={exampleRuler()}
        siblingSignals={[primary, sibling]}
        versionLabelFor={(id) => id}
      />,
    );
    expect(screen.queryByText(/\(faixa\)/)).not.toBeInTheDocument();
  });
});

describe("LabSignalPanel -> LabSignalDetail: the raw data (JSON) is fetched on demand (brief T3.24b: 'Ver envelope' -> 'Ver dados brutos (JSON)')", () => {
  it("calls the mocked action and shows the returned envelope as JSON when 'Ver dados brutos (JSON)' is clicked", async () => {
    loadLabSignalEnvelopeActionMock.mockResolvedValue({ ok: true, envelope: { rsi_14: "62.3", regime: "trend_up" } });
    render(<LabSignalPanel signal={exampleSignal()} versionLabel="momentum/v2" ruler={exampleRuler()} />);

    fireEvent.click(screen.getByRole("button", { name: "Ver dados brutos (JSON)" }));

    expect(await screen.findByText(/"rsi_14": "62.3"/)).toBeInTheDocument();
    expect(loadLabSignalEnvelopeActionMock).toHaveBeenCalledWith(
      exampleSignal().signal_id,
      exampleSignal().market,
      exampleSignal().strategy_version_id,
      exampleSignal().cohort,
    );
    expect(screen.getByRole("button", { name: "Ocultar dados brutos (JSON)" })).toBeInTheDocument();
  });

  it("shows the honest error reason instead of a blank panel when the action fails", async () => {
    loadLabSignalEnvelopeActionMock.mockResolvedValue({ ok: false, envelope: null, reason: "sinal não encontrado nesta página" });
    render(<LabSignalPanel signal={exampleSignal()} versionLabel="momentum/v2" ruler={exampleRuler()} />);

    fireEvent.click(screen.getByRole("button", { name: "Ver dados brutos (JSON)" }));

    expect(await screen.findByText(/sinal não encontrado nesta página/)).toBeInTheDocument();
  });
});
