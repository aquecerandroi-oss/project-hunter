"use client";

import { useRef, useState } from "react";

import { EXIT_REASON_LABEL } from "@/components/lab/lab-format";
import { BrasiliaInstant } from "@/components/time/brasilia-instant";
import { Badge } from "@/components/ui/badge";
import { useRowHeight } from "@/hooks/useDensity";
import { useVirtualizedRows } from "@/hooks/useVirtualizedRows";
import type { SignalListItemOut } from "@/lib/api/lab-types";
import type { DeskOut } from "@/lib/api/market-desk-types";
import type { MarketEventOut } from "@/lib/api/market-events-types";

import { deskOrderStatusLabel, MARKET_EVENT_CONFIDENCE_LABEL, MARKET_EVENT_KIND_LABEL, spotOrderReasonLabel } from "./labels";
import { eventEffectiveInstant } from "./confluence-window";

export interface ConfluenceEventListProps {
  signals: SignalListItemOut[];
  events: MarketEventOut[];
  desk: DeskOut | null;
  onSelectSignal: (signal: SignalListItemOut) => void;
  selectedSignalId: string | null;
}

type Row =
  | { kind: "signal"; iso: string; signal: SignalListItemOut }
  | { kind: "event"; iso: string; event: MarketEventOut }
  | { kind: "order"; iso: string; order: DeskOut["orders"][number] }
  | { kind: "position-entry" | "position-exit"; iso: string; position: DeskOut["positions"][number] };

/**
 * Code review, must-fix 4: this list used to render up to 500 `<tr>`
 * elements at once with a "showing the N most recent" cap past that --
 * project rule is virtualize at >= 200 rows (CLAUDE.md), and a cap is not
 * virtualization (it still drops rows, silently past 500). `useVirtualizedRows`/
 * `useRowHeight` are the same manual-windowing pair `lab-signals-grid.tsx`
 * uses for the Shadow Lab's own big table -- `@tanstack/react-virtual` is not
 * an installed dependency in this repo (confirmed: no `package.json` in the
 * workspace lists it), so this reuses the existing, already-tested pattern
 * instead of adding a new one for a single table.
 */
const VIEWPORT_HEIGHT = 480;
const OVERSCAN = 8;

/** A stable key even though two rows can legitimately share the same instant (two events at the same minute): the underlying entity's own id, never the array position. */
function rowKey(row: Row): string {
  if (row.kind === "signal") return `signal-${row.signal.signal_id}`;
  if (row.kind === "event") return `event-${row.event.id}`;
  if (row.kind === "order") return `order-${row.order.id}`;
  return `${row.kind}-${row.position.id}`;
}

function buildRows(signals: SignalListItemOut[], events: MarketEventOut[], desk: DeskOut | null): Row[] {
  const rows: Row[] = [];
  for (const signal of signals) rows.push({ kind: "signal", iso: signal.decision_at, signal });
  for (const event of events) rows.push({ kind: "event", iso: eventEffectiveInstant(event), event });
  for (const order of desk?.orders ?? []) rows.push({ kind: "order", iso: order.received_at, order });
  for (const position of desk?.positions ?? []) {
    rows.push({ kind: "position-entry", iso: position.entry_at, position });
    if (position.exit_at !== null) rows.push({ kind: "position-exit", iso: position.exit_at, position });
  }
  return rows.sort((a, b) => new Date(b.iso).getTime() - new Date(a.iso).getTime());
}

/**
 * Astra's round-4 review, must-fix 5: `useVirtualizedRows`' spacer math
 * assumes every row is exactly `rowHeight` tall -- `flex-wrap` on these
 * containers let a long headline/reason wrap onto a second line, growing the
 * real `<tr>` past that fixed height and desyncing the scroll position from
 * the computed indices (a jump/misalignment, not a crash). Every container
 * below is `flex-nowrap overflow-hidden` and the one genuinely unbounded
 * string in each row (a market event's title, a refusal's reason) is
 * `truncate` with the full text kept in `title=` -- honest ellipsis instead
 * of a silently broken virtualization invariant.
 */
function RowCells({ row, selectedSignalId, onSelectSignal }: { row: Row; selectedSignalId: string | null; onSelectSignal: (signal: SignalListItemOut) => void }) {
  if (row.kind === "signal") {
    return (
      <button type="button" onClick={() => onSelectSignal(row.signal)} className="flex flex-nowrap items-center gap-2 overflow-hidden text-left">
        <Badge variant="info">Lab</Badge>
        <Badge variant={row.signal.direction === "short" ? "negative" : "positive"}>{row.signal.direction}</Badge>
        <span className="shrink-0 text-fg">{EXIT_REASON_LABEL[row.signal.result]}</span>
        {row.signal.signal_id === selectedSignalId && <Badge variant="gold">selecionado</Badge>}
      </button>
    );
  }
  if (row.kind === "event") {
    return (
      <span className="flex flex-nowrap items-center gap-2 overflow-hidden">
        <Badge variant="outline">Notícia</Badge>
        <span className="shrink-0 text-fg-muted">{MARKET_EVENT_KIND_LABEL[row.event.kind as keyof typeof MARKET_EVENT_KIND_LABEL] ?? row.event.kind}</span>
        <span className="min-w-0 truncate text-fg" title={row.event.title}>{row.event.title}</span>
        <span className="shrink-0 text-fg-subtle">({MARKET_EVENT_CONFIDENCE_LABEL[row.event.confidence as keyof typeof MARKET_EVENT_CONFIDENCE_LABEL] ?? row.event.confidence})</span>
      </span>
    );
  }
  if (row.kind === "order") {
    const reason = row.order.status === "refused" ? spotOrderReasonLabel(row.order.reason) : null;
    return (
      <span className="flex flex-nowrap items-center gap-2 overflow-hidden">
        <Badge variant="gold">Nossa mesa</Badge>
        <span className="shrink-0 text-fg">{deskOrderStatusLabel(row.order.status)}</span>
        {reason !== null && <span className="min-w-0 truncate text-red" title={reason}>{reason}</span>}
      </span>
    );
  }
  const label = row.kind === "position-entry" ? "entrada real" : "saída real";
  return (
    <span className="flex flex-nowrap items-center gap-2 overflow-hidden">
      <Badge variant="gold">Nossa mesa</Badge>
      <span className="shrink-0 text-fg">{label}</span>
      {row.kind === "position-exit" && row.position.r_multiple !== null && (
        <span className="shrink-0 font-mono tabular-nums text-fg-muted">{Number(row.position.r_multiple) >= 0 ? "+" : ""}{Number(row.position.r_multiple).toFixed(2)}R</span>
      )}
    </span>
  );
}

/**
 * "A lista do período" (design §2): a mesma informação das faixas em tabela,
 * ordenada por instante decrescente -- o que sobrevive à impressão e à busca
 * com Ctrl+F. Real data only; an empty list says exactly that.
 */
export function ConfluenceEventList({ signals, events, desk, onSelectSignal, selectedSignalId }: ConfluenceEventListProps) {
  const rowHeight = useRowHeight();
  const [scrollTop, setScrollTop] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const allRows = buildRows(signals, events, desk);

  const { visibleRows, topPad, bottomPad } = useVirtualizedRows({
    rows: allRows,
    rowHeight,
    scrollTop,
    viewportHeight: VIEWPORT_HEIGHT,
    overscan: OVERSCAN,
  });

  if (allRows.length === 0) {
    return <p className="text-sm text-fg-muted">Nada registrado neste período para este mercado.</p>;
  }

  return (
    <div
      ref={containerRef}
      onScroll={(e) => setScrollTop(e.currentTarget.scrollTop)}
      className="rounded-md border border-border"
      style={{ height: VIEWPORT_HEIGHT, overflowY: "auto" }}
    >
      <table className="w-full text-left text-xs">
        <thead className="sticky top-0 bg-bg-overlay">
          <tr className="border-b border-border text-fg-muted">
            <th className="py-1 pr-2 font-medium">Instante</th>
            <th className="py-1 font-medium">O que aconteceu</th>
          </tr>
        </thead>
        <tbody>
          {topPad > 0 && (
            <tr aria-hidden="true" style={{ height: topPad }}>
              <td colSpan={2} />
            </tr>
          )}
          {visibleRows.map((row) => (
            <tr key={rowKey(row)} className="border-b border-border/40" style={{ height: rowHeight }}>
              {/*
                Astra's round-5 review, must-fix 5: NO vertical padding here on
                purpose -- `py-1.5` (12px) stacked on the `Badge`'s own 22px
                (line-height + padding + border, `ui/badge.tsx`) totals 34px,
                past the 32px compact `rowHeight` (`hooks/useDensity.ts`), so
                the real row grows past the height `useVirtualizedRows`
                budgeted for it. The default table-cell `vertical-align:
                middle` plus the `<tr>`'s own fixed `height` centers the
                content instead -- the same pattern `lab-signal-row.tsx`
                already uses for its own virtualized rows.
              */}
              <td className="whitespace-nowrap pr-2">
                <BrasiliaInstant iso={row.iso} className="font-mono tabular-nums text-fg-subtle" />
              </td>
              <td className="w-full max-w-0 overflow-hidden">
                <RowCells row={row} selectedSignalId={selectedSignalId} onSelectSignal={onSelectSignal} />
              </td>
            </tr>
          ))}
          {bottomPad > 0 && (
            <tr aria-hidden="true" style={{ height: bottomPad }}>
              <td colSpan={2} />
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
