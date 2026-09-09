"use client";

import { useTransition } from "react";
import { useRouter } from "next/navigation";
import Link, { useLinkStatus } from "next/link";

import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { formatCount } from "@/components/lab/lab-format";
import { LAB_SIGNALS_PAGE_SIZES, type LabSignalsPageRange, type LabSignalsPageSize } from "@/lib/api/lab-types";

export interface LabSignalPagerProps {
  /** 1-based `{from, to}` within the current tab's own ordering (T3.37 contract). */
  page: LabSignalsPageRange;
  /** `totals[state]` -- the real count for the currently active tab. */
  total: number;
  pageSize: LabSignalsPageSize;
  prevHref: string | null;
  nextHref: string | null;
  pageSizeHrefs: Record<LabSignalsPageSize, string>;
}

/** 1-based page number derived from the contract's own `page.from`/`pageSize` -- never a separately tracked counter that could drift from what the server actually returned. */
function pageNumber(from: number, pageSize: number): number {
  return from <= 0 ? 1 : Math.floor((from - 1) / pageSize) + 1;
}

/** Same reasoning as `lab-segment-tabs.tsx`'s `TabPendingMark` -- one `<Link>`, one sr-only marker for its own in-flight navigation. */
function PagerPendingMark() {
  const { pending } = useLinkStatus();
  if (!pending) return null;
  return <span className="sr-only"> (carregando)</span>;
}

/**
 * "1–200 de 2.135 · página 1" with "Próxima"/"Anterior" (brief T3.37,
 * replacing the old "Carregar mais" that only ever appended to a partial
 * page). "Anterior"/"Próxima" navigate via a real `<Link href>` (T3.51,
 * same reasoning as `lab-segment-tabs.tsx`: a `<button onClick={() =>
 * router.push(...)}>` has no fallback if its own transition never lands --
 * an `<a href>` still works). "Por página" stays a `<select>`, which cannot
 * itself be an anchor, so it keeps navigating via `router.push` -- the one
 * exception the brief calls out. An API failure surfaces as
 * `SectionUnavailable` for the whole "Sinais — Sombra" section
 * (`app/(app)/[orgSlug]/lab/page.tsx`'s own `loadSignals`, isolated from the
 * rest of the page like `loadScoreboard` already is), not a separate error
 * state owned by this component.
 */
export function LabSignalPager({ page, total, pageSize, prevHref, nextHref, pageSizeHrefs }: LabSignalPagerProps) {
  const router = useRouter();
  const [isPageSizePending, startTransition] = useTransition();

  function goToPageSize(href: string): void {
    startTransition(() => router.push(href));
  }

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-fg-muted">
      <p aria-live="polite">
        {total === 0
          ? "0 sinais nesta seleção"
          : `${formatCount(page.from)}–${formatCount(page.to)} de ${formatCount(total)} · página ${pageNumber(page.from, pageSize)}`}
        {isPageSizePending && " · carregando..."}
      </p>
      <div className="flex items-center gap-2">
        <label className="flex items-center gap-1.5">
          <span>Por página</span>
          <Select
            value={String(pageSize)}
            aria-label="Sinais por página"
            disabled={isPageSizePending}
            onChange={(event) => goToPageSize(pageSizeHrefs[Number(event.target.value) as LabSignalsPageSize])}
          >
            {LAB_SIGNALS_PAGE_SIZES.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </Select>
        </label>
        {prevHref ? (
          <Button asChild variant="outline" size="sm">
            <Link href={prevHref}>
              Anterior
              <PagerPendingMark />
            </Link>
          </Button>
        ) : (
          <Button type="button" variant="outline" size="sm" disabled>
            Anterior
          </Button>
        )}
        {nextHref ? (
          <Button asChild variant="outline" size="sm">
            <Link href={nextHref}>
              Próxima
              <PagerPendingMark />
            </Link>
          </Button>
        ) : (
          <Button type="button" variant="outline" size="sm" disabled>
            Próxima
          </Button>
        )}
      </div>
    </div>
  );
}
