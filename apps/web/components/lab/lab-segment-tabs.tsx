"use client";

import { useEffect, useTransition } from "react";
import { useRouter } from "next/navigation";

import { formatCount } from "@/components/lab/lab-format";
import { LAB_SEGMENT_LABEL, LAB_SEGMENTS, SEGMENT_TO_STATE, stateToSegment, type LabSegment } from "@/components/lab/lab-signal-segments";
import { logger } from "@/lib/logger";
import type { LabSignalsState, LabSignalsTotals } from "@/lib/api/lab-types";
import { cn } from "@/lib/utils";

// Finding 6 of the T3.38 review: warn once (never per render, never per tab)
// when an older API response omits `totals.distinct_operations` (contract
// T3.38) -- the fallback below stays honest either way (the raw signals
// count), but a missing field on a contract this screen depends on should
// never go unnoticed in the logs.
let warnedMissingDistinctOperations = false;

function warnOnceIfMissingDistinctOperations(totals: LabSignalsTotals): void {
  if (totals.distinct_operations !== undefined || warnedMissingDistinctOperations) return;
  warnedMissingDistinctOperations = true;
  logger.warn("lab_signals_totals_missing_distinct_operations", { all: totals.all });
}

export interface LabSegmentTabsProps {
  /** The API's own `state` -- the source of truth for which tab is active (never re-derived from the loaded rows). */
  state: LabSignalsState;
  /** Real counts over the whole filtered dataset (T3.37 contract's `totals`), never a count among only the ~200 rows currently loaded. */
  totals: LabSignalsTotals;
  /** One full href per segment, pre-built by `LabSignalsTable` via `buildLabHref` (a function prop cannot cross the Server->Client boundary, so the parent hands over plain strings instead). */
  hrefs: Record<LabSegment, string>;
}

/**
 * "Concluídas · Abertas · Pendentes/sem entrada · Todas" (brief T3.17b item
 * 4), now with real, whole-dataset counts (brief T3.37, Everton: "se tiver 2
 * mil operações tem que paginar mas mostrar as 2 mil") and server-side
 * navigation: clicking a tab rewrites `?state=` and lets the Server Component
 * refetch (`app/(app)/[orgSlug]/lab/page.tsx`) -- it never filters the
 * already-loaded page in the browser.
 */
export function LabSegmentTabs({ state, totals, hrefs }: LabSegmentTabsProps) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const activeSegment = stateToSegment(state);

  useEffect(() => {
    warnOnceIfMissingDistinctOperations(totals);
  }, [totals]);

  function handleSelect(segment: LabSegment): void {
    if (segment === activeSegment) return;
    startTransition(() => router.push(hrefs[segment]));
  }

  // brief T3.38 item 4: each tab still counts signals (the visible number,
  // unchanged) but its `title` also states the real unique-operations count
  // (contract T3.38's `totals.distinct_operations`) -- falls back to the
  // same signals count until T3.38a's field lands, so the tooltip is never
  // wrong, only uninformative in the interim.
  function tabTitle(segment: LabSegment): string {
    const state = SEGMENT_TO_STATE[segment];
    const signals = totals[state];
    const uniqueOps = totals.distinct_operations?.[state] ?? signals;
    return `${formatCount(signals)} sinais · ${formatCount(uniqueOps)} operações únicas`;
  }

  return (
    <div className="flex flex-col gap-1">
      <div role="tablist" aria-label="Filtrar sinais por estado" className="flex flex-wrap gap-1">
        {LAB_SEGMENTS.map((segment) => (
          <button
            key={segment}
            type="button"
            role="tab"
            aria-selected={activeSegment === segment}
            title={tabTitle(segment)}
            onClick={() => handleSelect(segment)}
            className={cn(
              "rounded-md border px-2.5 py-1 text-xs font-medium transition-colors",
              activeSegment === segment ? "border-gold bg-gold-soft text-gold" : "border-border text-fg-muted hover:text-fg",
            )}
          >
            {LAB_SEGMENT_LABEL[segment]} ({formatCount(totals[SEGMENT_TO_STATE[segment]])})
          </button>
        ))}
      </div>
      {/* Visually hidden -- announces the real, whole-dataset count on every
          tab change for a screen reader (brief T3.37: "aria-live on change"). */}
      {/* An em dash, not ":" -- "Pendentes/sem entrada" already ends in
          "entrada", so a colon here would read as the unrelated "sem
          entrada: <motivo>" chip text elsewhere on this page. */}
      <p aria-live="polite" className="sr-only">
        {isPending
          ? "carregando sinais..."
          : `${LAB_SEGMENT_LABEL[activeSegment]} — ${formatCount(totals[SEGMENT_TO_STATE[activeSegment]])} sinais no total`}
      </p>
    </div>
  );
}
