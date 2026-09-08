/**
 * Sibling-version grouping for the signals table (brief T3.38, Everton's
 * screenshot: `RAYSOLUSDT`, same bar/entry/exit/result, three rows --
 * `momentum/v2 pesquisa`, `momentum/v3 paper`, `momentum/v4 pesquisa` --
 * counted three times both in the table and in the totals card. "não tá
 * duplicando não??").
 *
 * Purely presentational and page-local: this module only ever sees the one
 * page of rows already loaded (`SignalListItemOut[]`), never reaches across
 * pages, and never re-derives Decimal equality itself -- it reads the
 * server-computed `identity_key` (contract T3.38, `lib/api/lab-types.ts`)
 * verbatim. A group only visually "merges" (chips instead of one strategy
 * cell) when it spans more than one distinct `strategy_version_id`; with a
 * single version selected, every group is a singleton by construction, so
 * nothing changes on screen (brief: "with a single version selected nothing
 * changes").
 */
import type { SignalListItemOut } from "@/lib/api/lab-types";

export interface LabSignalGroup {
  /** `identity_key` when present, else this row's own `signal_id` (see `identityKeyOf`'s doc) -- unique across the loaded page either way. */
  key: string;
  /** The first-loaded member -- the row whose market/prices/result the merged row displays (every member shares them by definition of `identity_key`). */
  primary: SignalListItemOut;
  /** Every signal in the group, in loaded order -- the per-version list a caller renders when expanding the row or its side panel. */
  members: SignalListItemOut[];
  /** Distinct `strategy_version_id`s among `members`, in first-seen order. */
  versionIds: string[];
}

/**
 * Contract T3.38: the API computes `identity_key` server-side from the
 * envelope. Until T3.38a lands (or for any row it happens to miss),
 * `identity_key` reading empty/undefined must never silently group unrelated
 * signals together -- each such row falls back to its own `signal_id`,
 * which is unique, so it stays its own singleton group instead.
 */
function identityKeyOf(row: SignalListItemOut): string {
  return row.identity_key ? `idk:${row.identity_key}` : `no-identity:${row.signal_id}`;
}

function uniqueInOrder(values: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const value of values) {
    if (!seen.has(value)) {
      seen.add(value);
      out.push(value);
    }
  }
  return out;
}

/**
 * Groups this page's own rows by `identity_key`, preserving the server's own
 * row order (a merged group sits at its first member's position; every other
 * occurrence of that key is skipped, never re-emitted later).
 *
 * A bucket only actually merges into one `LabSignalGroup` when it spans more
 * than one distinct `strategy_version_id` -- the brief's own sibling-version
 * scenario. A bucket whose rows all share one version never merges, even if
 * their `identity_key`s happen to coincide (e.g. two genuinely different
 * signals a backend bug or an untested edge case hashed the same): the brief
 * is explicit that "with a single version selected nothing changes", and
 * collapsing two same-version rows into one would silently drop a real row
 * from the table instead.
 */
export function groupSignalsByIdentity(rows: SignalListItemOut[]): LabSignalGroup[] {
  const byKey = new Map<string, SignalListItemOut[]>();
  for (const row of rows) {
    const key = identityKeyOf(row);
    const bucket = byKey.get(key);
    if (bucket) bucket.push(row);
    else byKey.set(key, [row]);
  }

  const emittedMergedKeys = new Set<string>();
  const result: LabSignalGroup[] = [];
  for (const row of rows) {
    const key = identityKeyOf(row);
    const members = byKey.get(key) as SignalListItemOut[];
    const versionIds = uniqueInOrder(members.map((m) => m.strategy_version_id));
    if (versionIds.length > 1) {
      if (emittedMergedKeys.has(key)) continue;
      emittedMergedKeys.add(key);
      result.push({ key, primary: members[0] as SignalListItemOut, members, versionIds });
    } else {
      result.push({ key: `${key}::${row.signal_id}`, primary: row, members: [row], versionIds: [row.strategy_version_id] });
    }
  }
  return result;
}

/** `true` once this page's own rows span more than one strategy version -- the gate the totals card/tab titles use before switching to "operações únicas" wording (brief items 3-4); a single-version page can never have a group spanning two versions, so this is always `false` there. */
export function hasMultipleVersions(rows: SignalListItemOut[]): boolean {
  return uniqueInOrder(rows.map((row) => row.strategy_version_id)).length > 1;
}

/**
 * Pure `identity_key` dedupe (finding 5 of the T3.38 review): the exact same
 * rule the server's own `totals.distinct_operations` counts by -- one row
 * per `identity_key`, in loaded order, regardless of how many distinct
 * `strategy_version_id`s share it. Deliberately *not* `groupSignalsByIdentity`'s
 * own rule (which only merges a bucket spanning more than one version, so
 * the *table* never silently drops a real row when a single-version page
 * happens to hash the same key twice) -- this function backs money math
 * only (the totals card's "desta página" scope): counting a same-version
 * duplicate as two operations there would disagree with the server's own
 * `totals.distinct_operations` for no visible reason, and "desta página"
 * vs. "de todas as concluídas" would silently diverge on a real duplicate.
 */
export function dedupeByIdentityKey(rows: SignalListItemOut[]): SignalListItemOut[] {
  const seen = new Set<string>();
  const out: SignalListItemOut[] = [];
  for (const row of rows) {
    const key = identityKeyOf(row);
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(row);
  }
  return out;
}
