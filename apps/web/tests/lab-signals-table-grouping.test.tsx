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
import { makeSignal } from "@/tests/fixtures/lab";

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
          totals: { closed: 3, open: 0, pending: 0, all: 3, distinct_operations: { closed: 1, open: 0, pending: 0, all: 1 } },
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

/**
 * Finding 2 of the T3.38 review: once merged, if a group's members still
 * disagree on R/money (should now be impossible once T3.38c-api's `stop`
 * fix is live -- this is the defensive, display-time case), the row shows
 * the real range instead of silently using the first member's value for
 * the whole group.
 */
describe("LabSignalsTable: a merged group with divergent R/money shows a range and a note, never just the first member (finding 2)", () => {
  it("the merged row's Resultado cell shows a range, and the totals card names the divergent operation instead of summing it silently", () => {
    const divergentSiblings = exampleSiblingSignals().map((row, i) => (i === 0 ? { ...row, r_multiple: "5.0000" } : row));
    render(
      <LabSignalsTable
        {...exampleLabSignalsTableProps({
          items: divergentSiblings,
          versionLabelById: SIBLING_VERSION_LABELS,
          totals: { closed: 3, open: 0, pending: 0, all: 3, distinct_operations: { closed: 1, open: 0, pending: 0, all: 1 } },
        })}
      />,
    );
    // Still one merged row (the visual-fusion rule is unchanged).
    expect(screen.getAllByText("RAYSOLUSDT")).toHaveLength(1);
    // The "Resultado" cell shows a range, not a single misleading figure.
    expect(screen.getByText("(faixa)")).toBeInTheDocument();
    // The totals card names the one divergent operation instead of silently
    // summing the first member's money as if it spoke for the group.
    const card = screen.getByTestId("lab-totals-card");
    expect(within(card).getByText(/1 operação com R\/dinheiro divergente/)).toBeInTheDocument();
  });

  it("never shows the divergence note when every merged group's members agree (the healthy, expected case)", () => {
    render(
      <LabSignalsTable
        {...exampleLabSignalsTableProps({
          items: exampleSiblingSignals(),
          versionLabelById: SIBLING_VERSION_LABELS,
          totals: { closed: 3, open: 0, pending: 0, all: 3 },
        })}
      />,
    );
    expect(screen.queryByText("(faixa)")).not.toBeInTheDocument();
    expect(screen.queryByText(/R\/dinheiro divergente/)).not.toBeInTheDocument();
  });
});

/**
 * Finding 5 of the T3.38 review: a same-version `identity_key` duplicate
 * never visually merges (the table's own T3.38b rule: never drop a real row
 * when a single-version page happens to hash the same key twice), but the
 * totals card's own money must still count it once -- the same pure-DISTINCT
 * rule the server's `totals.distinct_operations` uses.
 */
describe("LabSignalsTable: a same-version identity_key duplicate still shows two rows, but the card counts one operation (finding 5)", () => {
  it("keeps both rows on screen while the totals card's 'Operações' stat counts one", () => {
    const duplicateRows = [makeSignal({ signal_id: "dup-a", identity_key: "same-key" }), makeSignal({ signal_id: "dup-b", identity_key: "same-key" })];
    render(
      <LabSignalsTable
        {...exampleLabSignalsTableProps({
          items: duplicateRows,
          totals: { closed: 2, open: 0, pending: 0, all: 2, distinct_operations: { closed: 1, open: 0, pending: 0, all: 1 } },
        })}
      />,
    );
    // Two rows still show -- the visual-fusion rule never merges same-version rows.
    expect(screen.getAllByRole("row")).toHaveLength(3); // header + 2 data rows
    // The card's own money math counts the operation once, not twice.
    const card = screen.getByTestId("lab-totals-card");
    expect(within(card).getByText("Resultado das operações desta página (1 única de 2 linhas)")).toBeInTheDocument();
  });
});
