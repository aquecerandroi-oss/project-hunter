"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { EXIT_REASON_LABEL, reasonLabel } from "@/components/lab/lab-format";
import { MONEY_TOOLTIP, summarizeRows, totalsHeading, type MoneyRuler, type RowsSummary } from "@/components/lab/lab-money";
import type { SignalListItemOut } from "@/lib/api/lab-types";
import { formatBrlSigned, formatPct, formatUsdtSigned } from "@/lib/format";

export interface LabTotalsCardProps {
  rows: SignalListItemOut[];
  ruler: MoneyRuler;
  /** `true` when a `next_cursor` exists -- these totals cover only `rows`, never a number the API hasn't sent yet. */
  hasMore: boolean;
}

function Stat({ label, value, sub, colorClass }: { label: string; value: string; sub?: string | undefined; colorClass?: string | undefined }) {
  return (
    <div className="rounded-md border border-border p-3">
      <p className="text-xs font-medium uppercase text-fg-muted">{label}</p>
      <p className={`mt-1 font-mono text-xl tabular-nums ${colorClass ?? "text-fg"}`}>{value}</p>
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

function moneyOrReasonText(money: { value: number | null; reason: string | null }, formatValue: (value: number) => string): string {
  return money.value !== null ? formatValue(money.value) : reasonLabel(money.reason ?? "");
}

function highlightText(highlight: { market: string; pnlUsdt: number } | null): string {
  return highlight ? `${highlight.market} · ${formatUsdtSigned(highlight.pnlUsdt)}` : "—";
}

interface TotalsDisplay {
  resultUsdtText: string;
  resultBrlText: string;
  winRateText: string;
  avgProfitText: string;
  avgLossText: string;
  bestText: string;
  bestSub: string | undefined;
  worstText: string;
  worstSub: string | undefined;
}

/**
 * Every display string the card needs, computed once from `summarizeRows`'s
 * output -- kept as its own pure function (rather than inline in the
 * component) so `LabTotalsCard`'s own cyclomatic complexity stays under the
 * lint config's budget; this function is independently unit-testable too.
 */
function buildTotalsDisplay(summary: RowsSummary): TotalsDisplay {
  const winRateText =
    summary.winRate.value !== null
      ? `${formatPct(summary.winRate.value, { signed: false })} (${summary.withProfit}/${summary.withProfit + summary.withLoss})`
      : reasonLabel(summary.winRate.reason ?? "");

  return {
    resultUsdtText: moneyOrReasonText(summary.resultUsdt, formatUsdtSigned),
    resultBrlText: moneyOrReasonText(summary.resultBrl, formatBrlSigned),
    winRateText,
    avgProfitText: moneyOrReasonText(summary.avgProfitUsdt, formatUsdtSigned),
    avgLossText: moneyOrReasonText(summary.avgLossUsdt, formatUsdtSigned),
    bestText: highlightText(summary.best),
    bestSub: summary.best ? EXIT_REASON_LABEL[summary.best.result] : undefined,
    worstText: highlightText(summary.worst),
    worstSub: summary.worst ? EXIT_REASON_LABEL[summary.worst.result] : undefined,
  };
}

/**
 * "Operações · Com lucro/prejuízo · Taxa de acerto · Resultado acumulado" in
 * one compact row by default (brief T3.24b item [3]: four stats,
 * `grid-cols-2 sm:grid-cols-4`) -- the other eight (concluded/pending/no
 * entry/censored counts, per-page averages, best/worst operation) sit behind
 * a "Mais detalhes" toggle, collapsed by default so a first-time reader sees
 * the shape of the page before its full density. Computed client-side from
 * whatever `rows` are currently loaded in `LabSignalsTable`, never a second
 * fetch. Pending/no-entry/censored are counted and named separately, never
 * folded into "concluídas" (SHADOW-LAB.md's own three-axis state model: a
 * censored or no-entry tracking is not a win, a loss, or unresolved in the
 * same sense an `active` one is).
 *
 * Everton's own screenshot (T3.17b, "What Everton saw" item 1) called out the
 * old heading -- "resultado acumulado" alongside "há mais sinais além desta
 * página" -- as misleading: it read as if it covered the whole Lab. The
 * heading now says explicitly whether it covers "esta página" or, when the
 * list isn't truncated, "todas as operações do período"; the whole-Lab total
 * is T3.18's scoreboard, named below, never silently implied here.
 */
export function LabTotalsCard({ rows, ruler, hasMore }: LabTotalsCardProps) {
  const [expanded, setExpanded] = useState(false);
  const summary = summarizeRows(rows, ruler);
  const heading = totalsHeading(summary.total, hasMore);
  const display = buildTotalsDisplay(summary);

  return (
    <div data-testid="lab-totals-card" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-medium text-fg">{heading}</p>
        <Button type="button" variant="ghost" size="sm" aria-expanded={expanded} onClick={() => setExpanded((v) => !v)}>
          {expanded ? "Menos detalhes" : "Mais detalhes"}
        </Button>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Operações" value={String(summary.total)} />
        <Stat
          label="Com lucro / prejuízo"
          value={`${summary.withProfit} / ${summary.withLoss}`}
          colorClass={summary.withProfit > 0 || summary.withLoss > 0 ? "text-fg" : undefined}
        />
        <Stat label="Taxa de acerto" value={display.winRateText} />
        <Stat
          label="Resultado acumulado"
          value={display.resultUsdtText}
          sub={display.resultBrlText}
          colorClass={moneyColor(summary.resultUsdt.value)}
        />
      </div>

      {expanded && (
        <>
          <div data-testid="lab-totals-more" className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label="Concluídas" value={String(summary.completed)} />
            <Stat label="Pendentes" value={String(summary.pending)} />
            <Stat label="Sem entrada" value={String(summary.noEntry)} />
            <Stat label="Censuradas" value={String(summary.censored)} />
          </div>
          <div title={MONEY_TOOLTIP} className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label="Média com lucro (desta página)" value={display.avgProfitText} colorClass={summary.avgProfitUsdt.value !== null ? "text-green" : undefined} />
            <Stat label="Média com prejuízo (desta página)" value={display.avgLossText} colorClass={summary.avgLossUsdt.value !== null ? "text-red" : undefined} />
            <Stat
              label="Melhor operação (desta página)"
              value={display.bestText}
              sub={display.bestSub}
              colorClass={summary.best ? "text-green" : undefined}
            />
            <Stat
              label="Pior operação (desta página)"
              value={display.worstText}
              sub={display.worstSub}
              colorClass={summary.worst ? "text-red" : undefined}
            />
          </div>
        </>
      )}
    </div>
  );
}
