/**
 * The totals card's own scope-switch heading/note -- split out of
 * `lab-money.ts` (brief T3.38) to keep that file under the lint config's
 * 350-line budget rather than pushing it further over with this brief's own
 * additions. Pure, no I/O, same convention as the rest of `lab-money.ts`.
 */
export type TotalsScope = "page" | "allClosed";

export interface PageTotalsHeadingInput {
  /** `dedupeByIdentity(rows).length` -- the count the "page" scope's sums are actually over (brief T3.38 item 3: "first occurrence"). */
  uniqueCount: number;
  /** `rows.length` -- the loaded page's own raw row count, before folding sibling-version duplicates. */
  rowCount: number;
  /** `hasMultipleVersions(rows)` (`lab-signal-grouping.ts`) -- only once the page mixes versions does a duplicate become possible, so only then does the heading spell out "N únicas de M linhas" (brief T3.38 item 3). */
  versionsMixed: boolean;
}

/**
 * The totals card's own scope-switch heading (brief T3.37, replacing the old
 * `hasMore`-inferred wording from T3.17b item 1; extended by T3.38 item 3):
 * the reader now picks the scope explicitly ("desta página" | "de todas as
 * concluídas") instead of the card guessing from whether the page happened to
 * be truncated -- an inference that read wrong the moment a segment's real
 * total (T3.37's `totals.*`) exceeded the loaded page without the reader
 * knowing it. When the loaded page mixes strategy versions, "desta página"
 * spells out both counts ("N únicas de M linhas") so a reader never has to
 * wonder whether a sibling-version triplicate got summed three times.
 */
export function totalsHeading(scope: TotalsScope, page: PageTotalsHeadingInput, closedTotal: number): string {
  if (scope === "allClosed") return `Resultado de todas as operações concluídas (${closedTotal})`;
  if (page.versionsMixed) {
    const unica = page.uniqueCount === 1 ? "única" : "únicas";
    return `Resultado das operações desta página (${page.uniqueCount} ${unica} de ${page.rowCount} linhas)`;
  }
  return `Resultado das operações desta página (${page.rowCount})`;
}

/** The one-line note the totals card shows next to the heading when it mixes versions (brief T3.38 item 3, verbatim). */
export const SIBLING_VERSIONS_NOTE = "versões irmãs decidem a mesma barra; cada operação é contada uma vez";
