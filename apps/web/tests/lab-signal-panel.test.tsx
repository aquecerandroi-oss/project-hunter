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
import { exampleSignal, makeSignal } from "@/tests/fixtures/lab";

const versionLabelById = { "098b060c-cdc0-46a6-b88b-70d4a5472b97": "momentum/v2" };

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
    render(
      <LabSignalsTable
        orgSlug="acme"
        initialItems={[exampleSignal()]}
        initialCursor={null}
        baseParams={{ cohort: "prospective" }}
        versionLabelById={versionLabelById}
        cohort="prospective"
      />,
    );

    expect(screen.getByText(/Selecione um sinal na tabela/)).toBeInTheDocument();

    fireEvent.click(screen.getByText("AAAAUSDT").closest('[role="row"]') as HTMLElement);

    expect(screen.queryByText(/Selecione um sinal na tabela/)).not.toBeInTheDocument();
    // Panel-only content (the table row never shows a "Decisão:" label).
    expect(screen.getByText(/Decisão:/)).toBeInTheDocument();
  });

  it("also opens the panel on Enter (keyboard row navigation, hooks/useArrowKeyRowSelection)", () => {
    render(
      <LabSignalsTable
        orgSlug="acme"
        initialItems={[exampleSignal()]}
        initialCursor={null}
        baseParams={{ cohort: "prospective" }}
        versionLabelById={versionLabelById}
        cohort="prospective"
      />,
    );

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
    render(<LabSignalPanel signal={exampleSignal()} versionLabel="momentum/v2" />);

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
    render(<LabSignalPanel signal={signal} versionLabel="momentum/v2" />);

    const mfeRow = screen.getByText("MFE (favorável)").closest("div") as HTMLElement;
    expect(within(mfeRow).getByText(/1\.2500 price/)).toBeInTheDocument();
    expect(within(mfeRow).queryByText(/indeterminado/)).not.toBeInTheDocument();
    expect(screen.queryByText("ambíguo")).not.toBeInTheDocument();
  });
});

describe("LabSignalPanel -> LabSignalDetail: the envelope is fetched on demand and rendered as JSON", () => {
  it("calls the mocked action and shows the returned envelope as JSON when 'Ver envelope' is clicked", async () => {
    loadLabSignalEnvelopeActionMock.mockResolvedValue({ ok: true, envelope: { rsi_14: "62.3", regime: "trend_up" } });
    render(<LabSignalPanel signal={exampleSignal()} versionLabel="momentum/v2" />);

    fireEvent.click(screen.getByRole("button", { name: "Ver envelope" }));

    expect(await screen.findByText(/"rsi_14": "62.3"/)).toBeInTheDocument();
    expect(loadLabSignalEnvelopeActionMock).toHaveBeenCalledWith(
      exampleSignal().signal_id,
      exampleSignal().market,
      exampleSignal().strategy_version_id,
      exampleSignal().cohort,
    );
    expect(screen.getByRole("button", { name: "Ocultar envelope" })).toBeInTheDocument();
  });

  it("shows the honest error reason instead of a blank panel when the action fails", async () => {
    loadLabSignalEnvelopeActionMock.mockResolvedValue({ ok: false, envelope: null, reason: "sinal não encontrado nesta página" });
    render(<LabSignalPanel signal={exampleSignal()} versionLabel="momentum/v2" />);

    fireEvent.click(screen.getByRole("button", { name: "Ver envelope" }));

    expect(await screen.findByText(/sinal não encontrado nesta página/)).toBeInTheDocument();
  });
});
