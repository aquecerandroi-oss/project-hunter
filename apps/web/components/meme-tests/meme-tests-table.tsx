"use client";

import Link from "next/link";
import { useState } from "react";

import { formatSolSigned, signClass } from "@/components/meme-desk/meme-desk-format";
import { formatSol } from "@/components/meme/meme-format";
import type { MemeTestRow } from "@/lib/api/meme-tests-types";
import { formatBrasiliaLong } from "@/lib/time";

import { MemeTestRowDetail } from "./meme-test-row-detail";
import { formatBrasiliaClock, formatDurationSeconds, formatUsdSigned, rMultipleView, ruleSetLabel } from "./meme-tests-format";

export interface MemeTestsTableProps {
  orgSlug: string;
  /** Paper and REAL rows already merged newest-first (`mergeTestRows`); at most one API page (<= 200). */
  rows: MemeTestRow[];
}

const HEADERS = ["Hora entrada", "Moeda", "Conjunto", "Entrada SOL", "Saída SOL", "PnL SOL", "PnL US$", "R", "Motivo", "Duração"] as const;
const COLUMNS = HEADERS.length + 1;

/** The three left columns stay put while the rest scrolls (brief T4.13 §2 "colunas fixas à esquerda"); widths are fixed so the offsets never drift. */
const STICKY = ["sticky left-0 z-10 w-8 bg-bg-elevated", "sticky left-8 z-10 w-20 bg-bg-elevated", "sticky left-28 z-10 min-w-40 bg-bg-elevated"] as const;

const DASH = <span className="text-fg-subtle">—</span>;

export function KindBadge({ row }: { row: MemeTestRow }) {
  if (row.kind === "real_observed") {
    return (
      <span className="rounded-md bg-warning-soft px-1.5 py-0.5 text-[11px] font-medium text-warning" title={row.kind_label}>
        REAL — observado na cadeia
      </span>
    );
  }
  if (row.status === "open") return <span className="rounded-md bg-info-soft px-1.5 py-0.5 text-[11px] font-medium text-info">aberta</span>;
  return null;
}

function Cell({ children, className = "", title }: { children: React.ReactNode; className?: string; title?: string | undefined }) {
  return (
    <td className={`px-2 py-1.5 align-top ${className}`} title={title}>
      {children}
    </td>
  );
}

function IdentityCells({ orgSlug, row }: { orgSlug: string; row: MemeTestRow }) {
  return (
    <>
      <Cell className={`${STICKY[1]} font-mono tabular-nums`} title={formatBrasiliaLong(row.entry.at) ?? row.entry.at}>
        {formatBrasiliaClock(row.entry.at)}
      </Cell>
      <Cell className={STICKY[2]}>
        <Link href={`/${orgSlug}/meme/${row.mint}`} className="font-medium text-fg hover:underline">
          {row.token_name ?? "(nome desconhecido)"}
        </Link>
        <span className="ml-1 text-[11px] text-fg-subtle">{row.token_symbol ?? ""}</span>
        <div className="mt-0.5 flex flex-wrap gap-1">
          <KindBadge row={row} />
        </div>
      </Cell>
      <Cell className="font-mono text-fg-muted">{ruleSetLabel(row.rule_set.label)}</Cell>
    </>
  );
}

function MoneyCells({ row }: { row: MemeTestRow }) {
  const provisionalExit = row.exit.provisional ? " *" : "";
  const provisionalUsd = row.pnl_usd_basis === "entry_quote_provisional" ? " *" : "";
  const r = rMultipleView(row);
  return (
    <>
      <Cell className="text-right font-mono tabular-nums">{row.entry.sol_spent === null ? DASH : formatSol(row.entry.sol_spent)}</Cell>
      <Cell className="text-right font-mono tabular-nums" title={row.exit.provisional ? "saída provisória: a marca da última fotografia" : undefined}>
        {row.exit.sol_received === null ? DASH : `${formatSol(row.exit.sol_received)}${provisionalExit}`}
      </Cell>
      <Cell className={`text-right font-mono tabular-nums ${signClass(row.pnl_sol)}`}>{row.pnl_sol === null ? "—" : formatSolSigned(row.pnl_sol)}</Cell>
      <Cell className={`text-right font-mono tabular-nums ${row.pnl_usd === null ? "text-fg-subtle" : signClass(row.pnl_usd)}`}>
        {row.pnl_usd === null ? "sem cotação" : `${formatUsdSigned(row.pnl_usd)}${provisionalUsd}`}
      </Cell>
      <Cell className={`text-right font-mono tabular-nums ${r.muted ? "text-fg-muted" : signClass(row.r_multiple)}`} title={row.outcome_quality === "indeterminate" ? (row.outcome_quality_reason ?? undefined) : undefined}>
        {r.text}
      </Cell>
    </>
  );
}

function TestRow({ orgSlug, row, expanded, onToggle }: { orgSlug: string; row: MemeTestRow; expanded: boolean; onToggle: () => void }) {
  const detailId = `test-row-${row.id}`;
  return (
    <>
      <tr className="border-t border-border" data-kind={row.kind}>
        <Cell className={STICKY[0]}>
          <button
            type="button"
            aria-expanded={expanded}
            aria-controls={detailId}
            aria-label={expanded ? "recolher detalhes" : "expandir detalhes"}
            onClick={onToggle}
            className="rounded-sm px-1 text-fg-muted hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold"
          >
            {expanded ? "▾" : "▸"}
          </button>
        </Cell>
        <IdentityCells orgSlug={orgSlug} row={row} />
        <MoneyCells row={row} />
        <Cell className="text-fg-muted">{row.exit.reason_label}</Cell>
        <Cell className="font-mono tabular-nums text-fg-muted">{formatDurationSeconds(row.duration_s)}</Cell>
      </tr>
      {expanded && (
        <tr id={detailId} className="border-t border-border bg-bg-overlay/40">
          <td colSpan={COLUMNS} className="px-3 py-3">
            <MemeTestRowDetail orgSlug={orgSlug} row={row} />
          </td>
        </tr>
      )}
    </>
  );
}

function headerClass(index: number): string {
  const sticky = index === 0 ? STICKY[1] : index === 1 ? STICKY[2] : "";
  const align = index >= 3 && index <= 7 ? "text-right" : "";
  return `px-2 py-2 ${sticky} ${align}`;
}

/**
 * The dense record (13 px rows), one row per test, expandable in place.
 * Client island only for the expand state; sorting and filtering are the
 * page's (`?day=`, `?set=`). Never more than one API page (200 rows) -- the
 * section says so and points at the CSV for the whole day.
 */
export function MemeTestsTable({ orgSlug, rows }: MemeTestsTableProps) {
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  function toggle(id: string): void {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }
  return (
    <div className="overflow-x-auto rounded-md border border-border bg-bg-elevated">
      <table className="w-full text-left text-[13px]">
        <thead className="text-[11px] uppercase tracking-wide text-fg-muted">
          <tr>
            <th className={`px-2 py-2 ${STICKY[0]}`} aria-label="detalhes" />
            {HEADERS.map((header, index) => (
              <th key={header} className={headerClass(index)}>
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <TestRow key={row.id} orgSlug={orgSlug} row={row} expanded={expanded.has(row.id)} onToggle={() => toggle(row.id)} />
          ))}
        </tbody>
      </table>
    </div>
  );
}
