/**
 * The four completion signals of a token (T4.2d, migration 0024) as the
 * screen reads them -- pure, unit-tested in `tests/meme-graduation-signals.test.ts`.
 *
 * `completed_at` on the API is already the earliest of the four (a REST
 * "complete" with a zero reserve counting for nothing on its own); what this
 * module adds is the *disagreement*: some signals present and others absent
 * is the M-D2 finding of the plantão (72 of 140 "complete" coins were not on
 * the graduated board), and the brief asks for it in amber, never hidden
 * behind one state word.
 */
import type { MemeOverview, MemeToken } from "@/lib/api/meme-types";

import { COMPLETION_SIGNAL_KEYS, type CompletionSignalKey, type MemePoolSource, memeCompletionSignalLabel } from "./labels";

export interface CompletionSignal {
  key: CompletionSignalKey;
  label: string;
  /** ISO instant of the first sighting, or `null` when this radar never saw it. */
  at: string | null;
  /** Only on `pool_created`: who reported the pool first. */
  source?: MemePoolSource | null;
}

type SignalFields = Pick<
  MemeToken,
  "rest_complete_seen_at" | "curve_filled_seen_at" | "graduated_board_seen_at" | "pool_created_at" | "pool_created_source"
>;

/** The four, in the brief's order, each with its instant or `null`. A field an older payload left out is absent, never a date. */
export function completionSignals(token: SignalFields): CompletionSignal[] {
  const at: Record<CompletionSignalKey, string | null> = {
    rest_complete: token.rest_complete_seen_at ?? null,
    curve_filled: token.curve_filled_seen_at ?? null,
    graduated_board: token.graduated_board_seen_at ?? null,
    pool_created: token.pool_created_at ?? null,
  };
  return COMPLETION_SIGNAL_KEYS.map((key) => ({
    key,
    label: memeCompletionSignalLabel(key),
    at: at[key],
    ...(key === "pool_created" ? { source: token.pool_created_source ?? null } : {}),
  }));
}

/** Amber: at least one signal speaks and at least one is silent. No signal at all is "nothing to disagree about". */
export function signalsDisagree(signals: readonly CompletionSignal[]): boolean {
  const present = signals.filter((s) => s.at !== null).length;
  return present > 0 && present < signals.length;
}

export type GraduationMatrix = NonNullable<MemeOverview["graduation_matrix"]>;

type PairColumns = Pick<
  GraduationMatrix,
  "disagree_rest_filled" | "disagree_rest_board" | "disagree_rest_pool" | "disagree_filled_board" | "disagree_filled_pool" | "disagree_board_pool"
>;

/** The six pair disagreements summed -- the number the overview strip turns amber on. */
export function matrixDisagreements(matrix: PairColumns): number {
  return (
    matrix.disagree_rest_filled +
    matrix.disagree_rest_board +
    matrix.disagree_rest_pool +
    matrix.disagree_filled_board +
    matrix.disagree_filled_pool +
    matrix.disagree_board_pool
  );
}

export interface SignalMark {
  x: number;
  label: string;
}

/** Present signals as timestamped marks for the mcap chart; absent ones draw nothing. */
export function signalMarks(signals: readonly CompletionSignal[]): SignalMark[] {
  return signals.filter((s): s is CompletionSignal & { at: string } => s.at !== null).map((s) => ({ x: Date.parse(s.at), label: s.label }));
}
