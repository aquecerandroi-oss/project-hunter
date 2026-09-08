"use client";

import { useMemo, useState } from "react";

import { LabSegmentTabs } from "@/components/lab/lab-segment-tabs";
import { LabSignalPager } from "@/components/lab/lab-signal-pager";
import { LabSignalsEmpty } from "@/components/lab/lab-signals-empty";
import { LabSignalsGrid } from "@/components/lab/lab-signals-grid";
import { buildLabHref } from "@/components/lab/lab-signals-query";
import { LAB_SEGMENTS, SEGMENT_TO_STATE, stateToSegment, type LabSegment } from "@/components/lab/lab-signal-segments";
import { LabTotalsCard } from "@/components/lab/lab-totals-card";
import type { MoneyRuler } from "@/components/lab/lab-money";
import { Button } from "@/components/ui/button";
import { LAB_SIGNALS_PAGE_SIZES } from "@/lib/api/lab-types";
import type {
  LabSignalsPageRange,
  LabSignalsPageSize,
  LabSignalsState,
  LabSignalsTotals,
  LabSummaryOut,
  SignalListItemOut,
} from "@/lib/api/lab-types";

/**
 * The endpoint-scope fact (brief T3.17b item 2, revised T3.24b item [3]):
 * now a visible 11px line below the segment tabs, not a tooltip -- a reader
 * should not have to hover to learn the table's own period never matches the
 * "Janela do resumo" filter above it.
 */
const PERIOD_NOTE = "período: todo o disponível — a janela acima só filtra o resumo";

/**
 * The money-tooltip fact (brief T3.24b item [3]) moved out of every cell's
 * `title` and into this one visible line at the table's own footer -- a
 * simulated number should not need a hover to be labelled honestly.
 */
const MONEY_NOTE = "Valores simulados: dado real, custos assumidos, sem dinheiro.";

export interface LabSignalsTableProps {
  orgSlug: string;
  /** This page's own rows -- already filtered/ordered server-side by `state` (T3.37 contract); never re-filtered in the browser. */
  items: SignalListItemOut[];
  /** Real counts over the whole filtered dataset, independent of which page is loaded (T3.37 contract's `totals`). */
  totals: LabSignalsTotals;
  /** 1-based `{from, to}` of this page within the current `state`'s own ordering. */
  page: LabSignalsPageRange;
  pageSize: LabSignalsPageSize;
  nextCursor: string | null;
  /** The keyset cursors used to reach this page from page 1 -- see `buildLabHref`'s own doc for why this replaces a server-side "previous cursor". */
  cursorPath: string[];
  state: LabSignalsState;
  window: string;
  cohort: string;
  versionId: string | undefined;
  versionLabelById: Record<string, string>;
  ruler: MoneyRuler;
  /** `GET /lab/shadow/summary`'s own result (same cohort/window), reused by `LabTotalsCard`'s "de todas as concluídas" scope. */
  summary: LabSummaryOut;
}

/**
 * `/lab`'s signals list: virtualized (brief S3b, mirrors
 * `components/markets/markets-table.tsx`), server-paginated (T3.37: the
 * segment tabs and the pager both rewrite the page's own URL and let
 * `app/(app)/[orgSlug]/lab/page.tsx` refetch -- there is no client-side
 * accumulation or filtering of a partial page anymore), with a side detail
 * panel instead of per-row accordions (keeps every row the same height,
 * which the virtualization math requires).
 *
 * This endpoint does not accept `window`/`as_of` (contract-S3-lab.md) --
 * said explicitly below so it never looks like it shares the summary's
 * clock (Astra, S3b hierarchy review, must-fix).
 */
export function LabSignalsTable({
  orgSlug,
  items,
  totals,
  page,
  pageSize,
  nextCursor,
  cursorPath,
  state,
  window: labWindow,
  cohort,
  versionId,
  versionLabelById,
  ruler,
  summary,
}: LabSignalsTableProps) {
  const [showResearch, setShowResearch] = useState(false);
  const segment = stateToSegment(state);

  const versionLabelFor = useMemo(() => (id: string) => versionLabelById[id] ?? id, [versionLabelById]);

  const pathname = `/${orgSlug}/lab`;
  const hrefBase = { window: labWindow, cohort, versionId, pageSize };
  const segmentHrefs = useMemo(
    () =>
      Object.fromEntries(
        LAB_SEGMENTS.map((seg) => [seg, buildLabHref(pathname, { ...hrefBase, state: SEGMENT_TO_STATE[seg], cursorPath: [] })]),
      ) as Record<LabSegment, string>,
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [pathname, labWindow, cohort, versionId, pageSize],
  );
  const nextHref = nextCursor !== null ? buildLabHref(pathname, { ...hrefBase, state, cursorPath: [...cursorPath, nextCursor] }) : null;
  const prevHref = cursorPath.length > 0 ? buildLabHref(pathname, { ...hrefBase, state, cursorPath: cursorPath.slice(0, -1) }) : null;
  const pageSizeHrefs = useMemo(
    () =>
      Object.fromEntries(
        LAB_SIGNALS_PAGE_SIZES.map((size) => [size, buildLabHref(pathname, { window: labWindow, cohort, versionId, state, pageSize: size, cursorPath: [] })]),
      ) as Record<LabSignalsPageSize, string>,
    [pathname, labWindow, cohort, versionId, state],
  );

  if (totals.all === 0) return <LabSignalsEmpty cohort={cohort} />;

  // brief T3.38 item 3: "de todas as concluídas" uses the real, whole-dataset
  // unique-operations denominator once the API provides it (contract T3.38's
  // `totals.distinct_operations`) -- falls back to the raw `totals.closed`
  // (signals, not yet folded by identity) until T3.38a lands.
  const closedTotal = totals.distinct_operations?.closed ?? totals.closed;

  return (
    <div className="flex flex-col gap-4">
      <LabTotalsCard rows={items} ruler={ruler} summary={summary} versionId={versionId} closedTotal={closedTotal} />
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <LabSegmentTabs state={state} totals={totals} hrefs={segmentHrefs} />
          <Button type="button" variant="outline" size="sm" aria-pressed={showResearch} onClick={() => setShowResearch((v) => !v)}>
            {showResearch ? "Ocultar detalhes de pesquisa" : "Detalhes de pesquisa"}
          </Button>
        </div>
        <p className="text-[11px] text-fg-subtle">{PERIOD_NOTE}</p>
        {/* Keyed by the page's own identity (T3.37): a fresh mount per page
            resets scroll/selection naturally, instead of an effect calling
            setState on every tab/pager click (`LabSignalsGrid`'s own doc). */}
        <LabSignalsGrid
          key={`${state}-${page.from}-${pageSize}`}
          orgSlug={orgSlug}
          items={items}
          versionLabelFor={versionLabelFor}
          ruler={ruler}
          showResearch={showResearch}
          segment={segment}
        />
        <p className="text-[11px] text-fg-subtle">{MONEY_NOTE}</p>
        <LabSignalPager page={page} total={totals[state]} pageSize={pageSize} prevHref={prevHref} nextHref={nextHref} pageSizeHrefs={pageSizeHrefs} />
      </div>
    </div>
  );
}

