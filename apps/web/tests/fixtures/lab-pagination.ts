/**
 * T3.37 fixtures (state/page_size/cursor/totals/page) -- split out of
 * `tests/fixtures/lab.ts` to keep that file under the lint config's 350-line
 * budget rather than pushing it further over with this brief's own
 * additions.
 */
import type { LabSignalsTableProps } from "@/components/lab/lab-signals-table";
import type { LabSignalsPageRange, LabSignalsTotals } from "@/lib/api/lab-types";
import { exampleRuler, exampleSignal, exampleSummary } from "./lab";

/** Real, whole-dataset totals (never a per-page count); shaped after the brief's "929 evaluable" example, not the buggy counts it describes. */
export function exampleSignalsTotals(overrides: Partial<LabSignalsTotals> = {}): LabSignalsTotals {
  return { closed: 929, open: 340, pending: 866, all: 2135, ...overrides };
}

export function exampleSignalsPageRange(overrides: Partial<LabSignalsPageRange> = {}): LabSignalsPageRange {
  return { from: 1, to: 200, ...overrides };
}

/** Every `LabSignalsTable` prop, defaulted to a single-signal, page-1, "closed" state -- its test files override only the field each case cares about. */
export function exampleLabSignalsTableProps(overrides: Partial<LabSignalsTableProps> = {}): LabSignalsTableProps {
  return {
    orgSlug: "acme",
    items: [exampleSignal()],
    totals: exampleSignalsTotals(),
    page: exampleSignalsPageRange(),
    pageSize: 200,
    nextCursor: null,
    cursorPath: [],
    state: "closed",
    window: "30d",
    cohort: "prospective",
    versionId: undefined,
    versionLabelById: { "098b060c-cdc0-46a6-b88b-70d4a5472b97": "momentum/v2" },
    ruler: exampleRuler(),
    summary: exampleSummary(),
    ...overrides,
  };
}
