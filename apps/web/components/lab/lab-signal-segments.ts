/**
 * The segmented control from brief T3.17b item 4 ("What Everton saw" #4: a
 * fresh page of mostly-`pending`/`no_entry` rows pushed every concluded
 * operation off the first screen). Pure, unit-testable partition/sort logic
 * -- `lab-segment-tabs.tsx` only renders it.
 */
import type { LabSignalsState, SignalListItemOut } from "@/lib/api/lab-types";

export type LabSegment = "concluded" | "open" | "pending" | "all";

export const LAB_SEGMENTS: LabSegment[] = ["concluded", "open", "pending", "all"];

/**
 * T3.37: the web's own vocabulary (`LabSegment`, pt-BR labels below) mapped
 * 1:1 to the API's `state` query param (`LabSignalsState`) -- the backend
 * mirrors `matchesSegment`'s definitions below in SQL (brief T3.37, "read the
 * web file and mirror it in SQL"), so this mapping is the one place that
 * translates between the two vocabularies; `matchesSegment`/`segmentCounts`/
 * `sortSignalsConcludedFirst` themselves are UNCHANGED by T3.37 -- they stay
 * the canonical, independently-tested definition the backend reads, even
 * though `LabSignalsTable` no longer calls them to filter a page (the server
 * does that now).
 */
export const SEGMENT_TO_STATE: Record<LabSegment, LabSignalsState> = {
  concluded: "closed",
  open: "open",
  pending: "pending",
  all: "all",
};

export function stateToSegment(state: LabSignalsState): LabSegment {
  const entry = (Object.entries(SEGMENT_TO_STATE) as Array<[LabSegment, LabSignalsState]>).find(([, s]) => s === state);
  return entry ? entry[0] : "all";
}

export const LAB_SEGMENT_LABEL: Record<LabSegment, string> = {
  concluded: "Concluídas",
  open: "Abertas",
  pending: "Pendentes/sem entrada",
  all: "Todas",
};

/** "Pendentes/sem entrada" folds three `tracking_state`s together (pending_entry, no_entry, censored) -- none of them is a win, a loss, or a still-tracked position in the same sense `active` is (mirrors `lab-money.ts`'s own `TRACKING_BUCKET`, SHADOW-LAB.md's three-axis state model). */
export function matchesSegment(row: SignalListItemOut, segment: LabSegment): boolean {
  if (segment === "all") return true;
  if (segment === "concluded") return row.tracking_state === "terminal";
  if (segment === "open") return row.tracking_state === "active";
  return row.tracking_state === "pending_entry" || row.tracking_state === "no_entry" || row.tracking_state === "censored";
}

export function segmentCounts(rows: SignalListItemOut[]): Record<LabSegment, number> {
  const counts: Record<LabSegment, number> = { concluded: 0, open: 0, pending: 0, all: rows.length };
  for (const row of rows) {
    if (row.tracking_state === "terminal") counts.concluded++;
    else if (row.tracking_state === "active") counts.open++;
    else counts.pending++;
  }
  return counts;
}

function decisionAtDesc(a: SignalListItemOut, b: SignalListItemOut): number {
  return new Date(b.decision_at).getTime() - new Date(a.decision_at).getTime();
}

/**
 * Default order (brief item 4): `decision_at` desc, but every concluded
 * (`terminal`) row sorts before the rest, so a page dominated by fresh
 * pending signals never buries the concluded ones. Filtering any single
 * segment out of this ordered list preserves its own internal `decision_at`
 * desc order, since each segment is a subset of exactly one of the two
 * partitions sorted here.
 */
export function sortSignalsConcludedFirst(rows: SignalListItemOut[]): SignalListItemOut[] {
  const concluded = rows.filter((row) => row.tracking_state === "terminal").sort(decisionAtDesc);
  const rest = rows.filter((row) => row.tracking_state !== "terminal").sort(decisionAtDesc);
  return [...concluded, ...rest];
}

/** The rows a segment shows, in the table's actual display order -- the one function `LabSignalsTable` calls. */
export function visibleSignalsForSegment(rows: SignalListItemOut[], segment: LabSegment): SignalListItemOut[] {
  return sortSignalsConcludedFirst(rows).filter((row) => matchesSegment(row, segment));
}
