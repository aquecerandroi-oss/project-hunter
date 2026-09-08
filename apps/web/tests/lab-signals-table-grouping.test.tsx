import { cleanup, render, screen, within } from "@testing-library/react";
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
import { SIBLING_VERSIONS_NOTE } from "@/components/lab/lab-totals-heading";
import { exampleNearMissSignal, exampleLabSignalsTableProps, exampleSiblingSignals, SIBLING_VERSION_LABELS } from "@/tests/fixtures/lab-pagination";

beforeEach(() => {
  resolveMarketHrefActionMock.mockReset().mockResolvedValue("/acme/markets/binance/RAYSOLUSDT");
});

/**
 * Brief T3.38, Everton's own screenshot (08/09 15:16 Brasília): `RAYSOLUSDT`,
 * same bar/entry/exit/result, three sibling-version signals
 * (`momentum/v4 pesquisa`, `momentum/v2 pesquisa`, `momentum/v3 paper`)
 * counted three times both as rows and in the totals card. "não tá
 * duplicando não??" -- this file is the fixture-exact regression.
 */
describe("LabSignalsTable: identical sibling-version signals collapse into one row with version chips (brief T3.38)", () => {
  it("renders exactly one row for the three identical signals, with one chip per version", () => {
    render(
      <LabSignalsTable
        {...exampleLabSignalsTableProps({
          items: exampleSiblingSignals(),
          versionLabelById: SIBLING_VERSION_LABELS,
          totals: { closed: 3, open: 0, pending: 0, all: 3 },
        })}
      />,
    );
    // One market cell, not three.
    expect(screen.getAllByText("RAYSOLUSDT")).toHaveLength(1);
    // Three version chips on that one row.
    expect(screen.getByText("v4")).toBeInTheDocument();
    expect(screen.getByText("v2")).toBeInTheDocument();
    expect(screen.getByText("v3 paper")).toBeInTheDocument();
    // Exactly one data row (plus the header row).
    expect(screen.getAllByRole("row")).toHaveLength(2);
  });

  it("a near-miss (different exit) never joins the group -- two rows, two markets' worth of chips", () => {
    render(
      <LabSignalsTable
        {...exampleLabSignalsTableProps({
          items: [...exampleSiblingSignals(), exampleNearMissSignal()],
          versionLabelById: SIBLING_VERSION_LABELS,
          totals: { closed: 4, open: 0, pending: 0, all: 4 },
        })}
      />,
    );
    expect(screen.getAllByRole("row")).toHaveLength(3); // header + 2 data rows
    expect(screen.getByText("v3 paper")).toBeInTheDocument(); // the merged row
    expect(screen.getByText("momentum/v5")).toBeInTheDocument(); // the near-miss's own single-row strategy cell
  });

  it("with a single version in the loaded page, nothing changes -- no chips, one row per signal", () => {
    const rows = exampleSiblingSignals().map((row) => ({ ...row, strategy_version_id: "v2-id" }));
    render(
      <LabSignalsTable
        {...exampleLabSignalsTableProps({
          items: rows,
          versionLabelById: SIBLING_VERSION_LABELS,
          versionId: "v2-id",
          totals: { closed: 3, open: 0, pending: 0, all: 3 },
        })}
      />,
    );
    // Still three separate rows (all share identity_key, but only one version -> no merge).
    expect(screen.getAllByRole("row")).toHaveLength(4); // header + 3 data rows
    expect(screen.queryByText("v2 paper")).not.toBeInTheDocument();
  });

  it("the totals card sums the three duplicates as one unique operation and shows the sibling-versions note", () => {
    render(
      <LabSignalsTable
        {...exampleLabSignalsTableProps({
          items: exampleSiblingSignals(),
          versionLabelById: SIBLING_VERSION_LABELS,
          totals: { closed: 3, open: 0, pending: 0, all: 3 },
        })}
      />,
    );
    const card = screen.getByTestId("lab-totals-card");
    expect(within(card).getByText("Resultado das operações desta página (1 única de 3 linhas)")).toBeInTheDocument();
    expect(within(card).getByText(SIBLING_VERSIONS_NOTE)).toBeInTheDocument();
    // "Operações" stat counts the one unique operation, not three.
    expect(within(card).getByText("1")).toBeInTheDocument();
  });

  it("never shows the sibling note or the extended heading for an ordinary, single-version page", () => {
    render(<LabSignalsTable {...exampleLabSignalsTableProps()} />);
    expect(screen.queryByText(SIBLING_VERSIONS_NOTE)).not.toBeInTheDocument();
    expect(screen.getByText("Resultado das operações desta página (1)")).toBeInTheDocument();
  });
});
