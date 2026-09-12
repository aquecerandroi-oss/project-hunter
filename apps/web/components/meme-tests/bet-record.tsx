import Link from "next/link";

import { formatR, formatSolSigned, signClass } from "@/components/meme-desk/meme-desk-format";
import { MemeCurveChart } from "@/components/meme/meme-curve-chart";
import type { SignalMark } from "@/components/meme/meme-graduation-signals";
import { formatSol } from "@/components/meme/meme-format";
import { BrasiliaInstant } from "@/components/time/brasilia-instant";
import type { MemeTestDetail, MemeTestRow } from "@/lib/api/meme-tests-types";
import { formatBrasiliaDate } from "@/lib/time";

import { MemeTestRowDetail } from "./meme-test-row-detail";
import { formatDurationSeconds, formatUsdSigned, ruleSetLabel, testsHref } from "./meme-tests-format";

export interface BetRecordProps {
  orgSlug: string;
  detail: MemeTestDetail;
}

/** Entry and exit as the chart's marks -- the provisional exit (an open bet's mark) says so in its label. */
export function betMarks(detail: MemeTestDetail): SignalMark[] {
  const { row } = detail;
  const marks: SignalMark[] = [{ x: Date.parse(row.entry.at), label: "entrada" }];
  if (row.exit.at) marks.push({ x: Date.parse(row.exit.at), label: row.exit.provisional ? "marca atual (saída provisória)" : "saída" });
  return marks;
}

function dayOf(iso: string): string {
  const date = formatBrasiliaDate(iso);
  if (!date) return iso.slice(0, 10);
  const [d, m, y] = date.split("/");
  return `${y}-${m}-${d}`;
}

function StatCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-md border border-border p-3">
      <p className="text-xs uppercase tracking-wide text-fg-muted">{title}</p>
      {children}
    </div>
  );
}

function BetStats({ row }: { row: MemeTestRow }) {
  return (
    <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
      <StatCard title="Entrada">
        <BrasiliaInstant iso={row.entry.at} className="font-mono text-sm text-fg" />
        <p className="font-mono text-lg font-semibold tabular-nums text-fg">{row.entry.sol_spent === null ? "—" : formatSol(row.entry.sol_spent)}</p>
      </StatCard>
      <StatCard title={row.exit.provisional ? "Saída provisória" : "Saída"}>
        {row.exit.at ? <BrasiliaInstant iso={row.exit.at} className="font-mono text-sm text-fg" /> : <p className="text-sm text-fg-subtle">sem marca ainda</p>}
        <p className="font-mono text-lg font-semibold tabular-nums text-fg">{row.exit.sol_received === null ? "—" : formatSol(row.exit.sol_received)}</p>
      </StatCard>
      <StatCard title="PnL">
        <p className={`font-mono text-lg font-semibold tabular-nums ${signClass(row.pnl_sol)}`}>{row.pnl_sol === null ? "—" : formatSolSigned(row.pnl_sol)}</p>
        <p className={`font-mono text-sm tabular-nums ${row.pnl_usd === null ? "text-fg-subtle" : signClass(row.pnl_usd)}`}>{row.pnl_usd === null ? "sem cotação" : formatUsdSigned(row.pnl_usd)}</p>
      </StatCard>
      <StatCard title="R · duração">
        <p className={`font-mono text-lg font-semibold tabular-nums ${signClass(row.r_multiple)}`}>{row.r_multiple === null ? "—" : formatR(row.r_multiple)}</p>
        <p className="font-mono text-sm tabular-nums text-fg-muted">{formatDurationSeconds(row.duration_s)}</p>
      </StatCard>
    </section>
  );
}

/** `/meme/mesa/aposta/{id}` (brief T4.13 §3): the same record on its own page, with the curve between entry and exit and the two marks. */
export function BetRecord({ orgSlug, detail }: BetRecordProps) {
  const { row } = detail;
  const day = dayOf(row.entry.at);
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <p className="text-xs text-fg-muted">
          <Link href={testsHref({ orgSlug, host: "mesa", day })} className="underline">
            Testes de {formatBrasiliaDate(row.entry.at) ?? day}
          </Link>
        </p>
        <h1 className="text-xl font-semibold text-fg">
          {row.token_name ?? "(nome desconhecido)"} <span className="text-sm text-fg-muted">{row.token_symbol ?? ""}</span>
        </h1>
        <p className="text-xs text-fg-muted">
          {row.kind_label} · conjunto <span className="font-mono">{ruleSetLabel(row.rule_set.label)}</span> · {row.status === "open" ? "aberta" : "fechada"} · {row.exit.reason_label}
        </p>
        <p role="note" className="rounded-md border border-warning/40 bg-warning-soft px-3 py-2 text-xs font-medium text-warning">
          {detail.label}
        </p>
      </div>

      <BetStats row={row} />

      <section className="flex flex-col gap-2">
        <h2 className="text-sm font-medium text-fg">Curva entre a entrada e a saída</h2>
        <p className="text-[11px] text-fg-subtle">
          Fotografias de <BrasiliaInstant iso={detail.curve_from} /> a <BrasiliaInstant iso={detail.curve_to} /> ({detail.curve.length} ponto(s)); as marcas são a entrada e a saída.
        </p>
        <MemeCurveChart snapshots={detail.curve} marks={betMarks(detail)} />
      </section>

      <section className="flex flex-col gap-2 rounded-md border border-border p-3">
        <h2 className="text-sm font-medium text-fg">Ficha completa</h2>
        <MemeTestRowDetail orgSlug={orgSlug} row={row} withDetailLink={false} />
      </section>
    </div>
  );
}
