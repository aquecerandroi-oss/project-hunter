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
import { makeSignal } from "@/tests/fixtures/lab";

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
      />,
    );
    expect(screen.getByText("0 sinais nesta seleção.")).toBeInTheDocument();
  });
});

describe("LabSignalsTable: chips per tracking_state/result", () => {
  it("shows a 'sem entrada' chip with its reason for a no_entry row", () => {
    const row = makeSignal({ tracking_state: "no_entry", no_entry_reason: "late:delay", result: "invalidated" });
    render(
      <LabSignalsTable
        orgSlug="acme"
        initialItems={[row]}
        initialCursor={null}
        baseParams={{ cohort: "prospective" }}
        versionLabelById={versionLabelById}
        cohort="prospective"
      />,
    );
    expect(screen.getByText(/sem entrada:/)).toBeInTheDocument();
  });

  it("shows a 'censurado' chip with its reason for a censored row", () => {
    const row = makeSignal({ tracking_state: "censored", censored_reason: "gap:failed", result: "expired" });
    render(
      <LabSignalsTable
        orgSlug="acme"
        initialItems={[row]}
        initialCursor={null}
        baseParams={{ cohort: "prospective" }}
        versionLabelById={versionLabelById}
        cohort="prospective"
      />,
    );
    expect(screen.getByText(/censurado:/)).toBeInTheDocument();
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
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Carregar mais" }));

    expect(await screen.findByText("Shadow Lab indisponível")).toBeInTheDocument();
    expect(screen.getByText("AAAAUSDT")).toBeInTheDocument();
  });
});

describe("LabSignalsTable: the endpoint's own window scope is stated, not implied", () => {
  it("says signals cover the whole available period, distinct from the summary's window filter", () => {
    render(
      <LabSignalsTable
        orgSlug="acme"
        initialItems={[makeSignal()]}
        initialCursor={null}
        baseParams={{ cohort: "prospective" }}
        versionLabelById={versionLabelById}
        cohort="prospective"
      />,
    );
    expect(screen.getByText(/todo o período disponível/)).toBeInTheDocument();
  });
});
