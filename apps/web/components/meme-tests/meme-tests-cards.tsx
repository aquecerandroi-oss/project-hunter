import Link from "next/link";

import { formatSolSigned, signClass } from "@/components/meme-desk/meme-desk-format";
import { formatSol } from "@/components/meme/meme-format";
import type { MemeTestRow } from "@/lib/api/meme-tests-types";
import { formatBrasiliaLong } from "@/lib/time";

import { MemeTestRowDetail } from "./meme-test-row-detail";
import { formatBrasiliaClock, formatDurationSeconds, formatUsdSigned, rMultipleView, ruleSetLabel } from "./meme-tests-format";

export interface MemeTestsCardsProps {
  orgSlug: string;
  rows: MemeTestRow[];
}

function Num({ label, value, className = "text-fg" }: { label: string; value: string; className?: string }) {
  return (
    <div>
      <p className="text-[11px] uppercase tracking-wide text-fg-subtle">{label}</p>
      <p className={`font-mono text-[13px] tabular-nums ${className}`}>{value}</p>
    </div>
  );
}

function CardNumbers({ row }: { row: MemeTestRow }) {
  const r = rMultipleView(row);
  return (
    <div className="mt-2 grid grid-cols-3 gap-2">
      <Num label="Entrada" value={row.entry.sol_spent === null ? "—" : formatSol(row.entry.sol_spent)} />
      <Num label={row.exit.provisional ? "Saída *" : "Saída"} value={row.exit.sol_received === null ? "—" : formatSol(row.exit.sol_received)} />
      <Num label="PnL SOL" value={row.pnl_sol === null ? "—" : formatSolSigned(row.pnl_sol)} className={signClass(row.pnl_sol)} />
      <Num label="PnL US$" value={row.pnl_usd === null ? "sem cotação" : formatUsdSigned(row.pnl_usd)} className={row.pnl_usd === null ? "text-fg-subtle" : signClass(row.pnl_usd)} />
      <Num label="R" value={r.text} className={r.muted ? "text-fg-muted" : signClass(row.r_multiple)} />
      <Num label="Duração" value={formatDurationSeconds(row.duration_s)} className="text-fg-muted" />
    </div>
  );
}

function CardHeader({ orgSlug, row }: { orgSlug: string; row: MemeTestRow }) {
  return (
    <>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="flex flex-wrap items-baseline gap-2">
          <span className="font-mono tabular-nums text-fg" title={formatBrasiliaLong(row.entry.at) ?? row.entry.at}>
            {formatBrasiliaClock(row.entry.at)}
          </span>
          <Link href={`/${orgSlug}/meme/${row.mint}`} className="text-sm font-medium text-fg hover:underline">
            {row.token_name ?? "(nome desconhecido)"}
          </Link>
        </span>
        <span className="font-mono text-[11px] text-fg-muted">{ruleSetLabel(row.rule_set.label)}</span>
      </div>
      <div className="mt-1 flex flex-wrap gap-1">
        {row.kind === "real_observed" && <span className="rounded-md bg-warning-soft px-1.5 py-0.5 text-[11px] font-medium text-warning">REAL — observado na cadeia</span>}
        {row.status === "open" && <span className="rounded-md bg-info-soft px-1.5 py-0.5 text-[11px] font-medium text-info">aberta</span>}
      </div>
    </>
  );
}

function TestCard({ orgSlug, row }: { orgSlug: string; row: MemeTestRow }) {
  return (
    <li className="rounded-md border border-border p-3 text-xs" data-kind={row.kind}>
      <CardHeader orgSlug={orgSlug} row={row} />
      <CardNumbers row={row} />
      <p className="mt-2 text-fg-muted">
        {row.exit.reason_label}
        {row.exit.at ? ` · saiu ${formatBrasiliaClock(row.exit.at)}` : ""}
      </p>
      <details className="mt-2">
        <summary className="cursor-pointer text-fg-muted">Detalhes</summary>
        <div className="mt-2">
          <MemeTestRowDetail orgSlug={orgSlug} row={row} />
        </div>
      </details>
    </li>
  );
}

/** The 375 px layout (brief T4.13 §2): one card per test with the six numbers that matter and a native `<details>` for the rest -- no JS needed. */
export function MemeTestsCards({ orgSlug, rows }: MemeTestsCardsProps) {
  return (
    <ul className="flex flex-col gap-2">
      {rows.map((row) => (
        <TestCard key={row.id} orgSlug={orgSlug} row={row} />
      ))}
    </ul>
  );
}
