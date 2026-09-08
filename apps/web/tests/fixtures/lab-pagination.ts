/**
 * T3.37 fixtures (state/page_size/cursor/totals/page) -- split out of
 * `tests/fixtures/lab.ts` to keep that file under the lint config's 350-line
 * budget rather than pushing it further over with this brief's own
 * additions.
 */
import type { LabSignalsTableProps } from "@/components/lab/lab-signals-table";
import type { LabSignalsPageRange, LabSignalsTotals, SignalListItemOut } from "@/lib/api/lab-types";
import { exampleRuler, exampleSignal, exampleSummary, makeSignal } from "./lab";

/** Real, whole-dataset totals (never a per-page count); shaped after the brief's "929 evaluable" example, not the buggy counts it describes. */
export function exampleSignalsTotals(overrides: Partial<LabSignalsTotals> = {}): LabSignalsTotals {
  return { closed: 929, open: 340, pending: 866, all: 2135, ...overrides };
}

export function exampleSignalsPageRange(overrides: Partial<LabSignalsPageRange> = {}): LabSignalsPageRange {
  return { from: 1, to: 200, ...overrides };
}

/**
 * T3.38 fixture -- Everton's own screenshot (VPS, 08/09 15:16 Brasília):
 * `RAYSOLUSDT`, same bar, same entry `1.16930116`, same exit
 * `1.1865126569 · alvo`, same `+34,00 USDT` -- three rows,
 * `momentum/v4 pesquisa`, `momentum/v2 pesquisa`, `momentum/v3 paper` (v3 a
 * byte-identical paper copy of v2; v4 = v2 + a stricter `atr_pct_min` this
 * signal still passed), in that measured order. `identity_key` is the same
 * across all three (contract T3.38) -- only `strategy_version_id`/`purpose`
 * differ.
 */
export function exampleSiblingSignals(): SignalListItemOut[] {
  const shared: Partial<SignalListItemOut> = {
    market: "RAYSOLUSDT",
    source_bar_close: "2026-09-08T15:00:00Z",
    decision_at: "2026-09-08T15:00:01Z",
    virtual_entry: "1.1693011600",
    entry_ts: "2026-09-08T15:01:00Z",
    exit_price: "1.1865126569",
    exit_ts: "2026-09-08T16:10:00Z",
    result: "target",
    tracking_state: "terminal",
    r_multiple: "1.0000",
    identity_key: "idk-raysolusdt-shared",
  };
  return [
    makeSignal({ ...shared, signal_id: "sig-v4", strategy_version_id: "v4-id", purpose: "research_only" }),
    makeSignal({ ...shared, signal_id: "sig-v2", strategy_version_id: "v2-id", purpose: "research_only" }),
    makeSignal({ ...shared, signal_id: "sig-v3", strategy_version_id: "v3-id", purpose: "paper" }),
  ];
}

/** The brief's own "near-miss" case: same market/version-mix shape, but a different exit -- a real different operation, `identity_key` differs, never grouped with `exampleSiblingSignals()`. */
export function exampleNearMissSignal(overrides: Partial<SignalListItemOut> = {}): SignalListItemOut {
  return makeSignal({
    signal_id: "sig-v5-near-miss",
    strategy_version_id: "v5-id",
    market: "RAYSOLUSDT",
    source_bar_close: "2026-09-08T15:00:00Z",
    virtual_entry: "1.1693011600",
    exit_price: "1.2000000000",
    result: "target",
    tracking_state: "terminal",
    r_multiple: "1.5000",
    identity_key: "idk-raysolusdt-near-miss",
    purpose: "research_only",
    ...overrides,
  });
}

/** `versionLabelById` entries for the three sibling versions above, same `"<strategy_key>/<version>"` shape `lab-page-body.tsx` builds. */
export const SIBLING_VERSION_LABELS: Record<string, string> = {
  "v2-id": "momentum/v2",
  "v3-id": "momentum/v3",
  "v4-id": "momentum/v4",
  "v5-id": "momentum/v5",
};

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
