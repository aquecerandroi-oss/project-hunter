/**
 * Pure query-string builder for `/lab`'s signals section (brief T3.37b):
 * the segment tabs and the pager both navigate by rewriting the page's own
 * URL (mirrors `lab-filters.tsx`'s established convention) instead of
 * filtering an already-loaded, partial page client-side. Kept as its own
 * module -- rather than inline in `lab-signals-table.tsx` -- so the exact
 * href a click produces is independently unit-testable without mounting a
 * component.
 */
import type { LabSignalsPageSize, LabSignalsState } from "@/lib/api/lab-types";

export interface LabHrefParams {
  window: string;
  cohort: string;
  versionId: string | undefined;
  state: LabSignalsState;
  pageSize: LabSignalsPageSize;
  /**
   * The keyset cursors used to reach every page after page 1, in visiting
   * order (page 2's cursor first) -- there is no server-provided "previous
   * cursor" (T3.37a's own keyset, `(decision_at DESC, id DESC)`), so
   * "Anterior" is this stack's own `slice(0, -1)` and "Próxima" is this
   * stack plus the current page's `next_cursor`. Empty means page 1.
   */
  cursorPath: string[];
}

/** `prospective` is the signals endpoint's own default (mirrors `lab-filters.tsx`'s cohort omission rule) -- never written to the URL when it is the value in effect. */
export function buildLabHref(pathname: string, params: LabHrefParams): string {
  const search = new URLSearchParams();
  search.set("window", params.window);
  if (params.cohort && params.cohort !== "prospective") search.set("cohort", params.cohort);
  if (params.versionId) search.set("version", params.versionId);
  search.set("state", params.state);
  search.set("page_size", String(params.pageSize));
  for (const cursor of params.cursorPath) search.append("c", cursor);
  return `${pathname}?${search.toString()}`;
}
