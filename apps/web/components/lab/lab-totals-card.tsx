import { reasonLabel } from "@/components/lab/lab-format";
import { MONEY_TOOLTIP, summarizeRows, truncationNote, type MoneyRuler } from "@/components/lab/lab-money";
import type { SignalListItemOut } from "@/lib/api/lab-types";
import { formatBrlSigned, formatPct, formatUsdtSigned } from "@/lib/format";

export interface LabTotalsCardProps {
  rows: SignalListItemOut[];
  ruler: MoneyRuler;
  /** `true` when a `next_cursor` exists -- these totals cover only `rows`, never a number the API hasn't sent yet. */
  hasMore: boolean;
}

function Stat({ label, value, sub, colorClass }: { label: string; value: string; sub?: string; colorClass?: string | undefined }) {
  return (
    <div className="rounded-md border border-border p-3">
      <p className="text-xs font-medium uppercase text-fg-muted">{label}</p>
      <p className={`mt-1 font-mono text-lg tabular-nums ${colorClass ?? "text-fg"}`}>{value}</p>
      {sub && <p className="mt-0.5 text-[11px] text-fg-subtle">{sub}</p>}
    </div>
  );
}

function moneyColor(value: number | null): string {
  if (value === null) return "text-fg-muted";
  if (value > 0) return "text-green";
  if (value < 0) return "text-red";
  return "text-fg";
}

/**
 * "Operações simuladas · Concluídas · Com lucro / Com prejuízo · Resultado
 * acumulado · Taxa de acerto" (brief T3.17 item 2) -- computed client-side
 * from whatever `rows` are currently loaded in `LabSignalsTable`, never a
 * second fetch. Pending/no-entry/censored are counted and named separately,
 * never folded into "concluídas" (SHADOW-LAB.md's own three-axis state
 * model: a censored or no-entry tracking is not a win, a loss, or unresolved
 * in the same sense an `active` one is).
 */
export function LabTotalsCard({ rows, ruler, hasMore }: LabTotalsCardProps) {
  const summary = summarizeRows(rows, ruler);
  const note = truncationNote(rows.length, hasMore);

  const resultUsdtText = summary.resultUsdt.value !== null ? formatUsdtSigned(summary.resultUsdt.value) : reasonLabel(summary.resultUsdt.reason ?? "");
  const resultBrlText =
    summary.resultBrl.value !== null ? formatBrlSigned(summary.resultBrl.value) : reasonLabel(summary.resultBrl.reason ?? "");
  const winRateText =
    summary.winRate.value !== null
      ? `${formatPct(summary.winRate.value, { signed: false })} (${summary.withProfit}/${summary.withProfit + summary.withLoss})`
      : reasonLabel(summary.winRate.reason ?? "");

  return (
    <div data-testid="lab-totals-card" className="flex flex-col gap-2">
      {note && <p className="text-xs text-fg-muted">{note}</p>}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Stat label="Operações simuladas" value={String(summary.total)} />
        <Stat label="Concluídas" value={String(summary.completed)} />
        <Stat label="Com lucro" value={String(summary.withProfit)} colorClass={summary.withProfit > 0 ? "text-green" : undefined} />
        <Stat label="Com prejuízo" value={String(summary.withLoss)} colorClass={summary.withLoss > 0 ? "text-red" : undefined} />
        <Stat
          label="Pendentes / sem entrada / censuradas"
          value={`${summary.pending} / ${summary.noEntry} / ${summary.censored}`}
        />
        <Stat label="Taxa de acerto" value={winRateText} />
      </div>
      <div title={MONEY_TOOLTIP} className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Stat label="Resultado acumulado (USDT)" value={resultUsdtText} colorClass={moneyColor(summary.resultUsdt.value)} />
        <Stat label="Resultado acumulado (BRL)" value={resultBrlText} colorClass={moneyColor(summary.resultBrl.value)} />
      </div>
    </div>
  );
}
