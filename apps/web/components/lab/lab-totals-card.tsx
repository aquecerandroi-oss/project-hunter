"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { EXIT_REASON_LABEL, formatCount, reasonLabel } from "@/components/lab/lab-format";
import {
  combineClosedSumRUsdt,
  MONEY_TOOLTIP,
  summarizeRows,
  usdtToBrl,
  type MoneyRuler,
  type RowsSummary,
} from "@/components/lab/lab-money";
import { dedupeByIdentity, hasMultipleVersions } from "@/components/lab/lab-signal-grouping";
import { SIBLING_VERSIONS_NOTE, totalsHeading, type TotalsScope } from "@/components/lab/lab-totals-heading";
import type { LabSummaryOut, SignalListItemOut, VersionSummaryOut } from "@/lib/api/lab-types";
import { formatBrlSigned, formatPct, formatUsdtSigned } from "@/lib/format";

export interface LabTotalsCardProps {
  /** The currently loaded page's own rows -- the "desta página" scope, exactly as before T3.37. */
  rows: SignalListItemOut[];
  ruler: MoneyRuler;
  /**
   * `GET /lab/shadow/summary`'s own already-fetched result for the same
   * cohort/window (`app/(app)/[orgSlug]/lab/page.tsx` fetches it once, up top
   * -- reused here rather than a second client fetch, since "the same
   * filters" the brief asks for are already on the page). Backs the "de
   * todas as concluídas" scope -- never a client sum of a page (brief T3.37).
   */
  summary: LabSummaryOut;
  /** Narrows `summary.versions` to the one the signals list is filtered to, when a version filter is active. */
  versionId: string | undefined;
  /** `totals.closed` (T3.37 contract) -- the real count of concluded signals over the whole filtered dataset, independent of which page is loaded. */
  closedTotal: number;
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

interface AllClosedDisplay {
  resultText: string;
  resultBrlText: string | undefined;
  resultColor: string;
  winRateText: string;
}

/**
 * Single-version win rate is a real API number (`net_profit_rate`); combined
 * across several versions it would need each one's own numerator/denominator
 * (not in this schema) to weight correctly -- shown honestly as unavailable
 * instead of a fabricated average (brief T3.37).
 */
function singleVersionWinRateText(versions: VersionSummaryOut[]): string {
  if (versions.length !== 1) return reasonLabel("not_aggregable_across_versions");
  const [only] = versions;
  if (!only) return reasonLabel("not_aggregable_across_versions");
  const rate = only.metrics.net_profit_rate;
  return moneyOrReasonText({ value: rate.value !== null ? Number(rate.value) : null, reason: rate.reason }, (v) => formatPct(v, { signed: false }));
}

/**
 * Every display string the "de todas as concluídas" scope needs, computed
 * once (rather than inline in the component) so `LabTotalsCard`'s own
 * cyclomatic complexity stays under the lint config's budget -- mirrors
 * `buildTotalsDisplay`'s own split for the "page" scope.
 */
function buildAllClosedDisplay(summary: LabSummaryOut, versionId: string | undefined, ruler: MoneyRuler): AllClosedDisplay {
  const relevantVersions = versionId ? summary.versions.filter((v) => v.strategy_version_id === versionId) : summary.versions;
  const result = combineClosedSumRUsdt(relevantVersions, ruler);
  const resultBrl = result.value !== null ? usdtToBrl(result.value, ruler) : null;
  return {
    resultText: moneyOrReasonText(result, formatUsdtSigned),
    resultBrlText: resultBrl !== null ? formatBrlSigned(resultBrl) : undefined,
    resultColor: moneyColor(result.value),
    winRateText: singleVersionWinRateText(relevantVersions),
  };
}

/** Extracted out of `LabTotalsCard` (rather than an inline `&&` chain) so that component's own cyclomatic complexity stays under the lint config's budget -- brief T3.38 item 3's one-line note, page scope only, mixed versions only. */
function SiblingVersionsNote({ scope, versionsMixed }: { scope: TotalsScope; versionsMixed: boolean }) {
  if (scope !== "page" || !versionsMixed) return null;
  return <p className="text-[11px] text-fg-subtle">{SIBLING_VERSIONS_NOTE}</p>;
}

/** The two-button scope switch (brief T3.37): "desta página" is the exact same client math T3.17b already shipped; "de todas as concluídas" never sums a page -- see `combineClosedSumRUsdt`. */
function ScopeSwitch({ scope, onChange }: { scope: TotalsScope; onChange: (scope: TotalsScope) => void }) {
  return (
    <div role="group" aria-label="Escopo do resultado" className="flex gap-1">
      {(
        [
          ["page", "Desta página"],
          ["allClosed", "De todas as concluídas"],
        ] as const
      ).map(([value, label]) => (
        <button
          key={value}
          type="button"
          aria-pressed={scope === value}
          onClick={() => onChange(value)}
          className={`rounded-md border px-2 py-1 text-[11px] font-medium transition-colors ${
            scope === value ? "border-gold bg-gold-soft text-gold" : "border-border text-fg-muted hover:text-fg"
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

/**
 * "Operações · Com lucro/prejuízo · Taxa de acerto · Resultado acumulado" in
 * one compact row by default (brief T3.24b item [3]: four stats,
 * `grid-cols-2 sm:grid-cols-4`) -- the other eight (concluded/pending/no
 * entry/censored counts, per-page averages, best/worst operation) sit behind
 * a "Mais detalhes" toggle, collapsed by default so a first-time reader sees
 * the shape of the page before its full density. Pending/no-entry/censored
 * are counted and named separately, never folded into "concluídas"
 * (SHADOW-LAB.md's own three-axis state model: a censored or no-entry
 * tracking is not a win, a loss, or unresolved in the same sense an `active`
 * one is).
 *
 * T3.37 (Everton: "se tiver 2 mil operações tem que paginar mas mostrar as 2
 * mil") added the explicit scope switch below: "desta página" is exactly the
 * page-bound math T3.17b already shipped (`summarizeRows` over `rows`);
 * "de todas as concluídas" is the real, whole-dataset figure instead of the
 * old `hasMore`-inferred heading, which silently mislabeled a truncated
 * period as "todas as operações" whenever the loaded page happened to be
 * shorter than the page size.
 */
export function LabTotalsCard({ rows, ruler, summary, versionId, closedTotal }: LabTotalsCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [scope, setScope] = useState<TotalsScope>("page");
  // brief T3.38 item 3: a page that mixes sibling-version duplicates sums
  // each real operation once (first occurrence), never once per version.
  const versionsMixed = hasMultipleVersions(rows);
  const uniqueRows = dedupeByIdentity(rows);
  const pageSummary = summarizeRows(uniqueRows, ruler);
  const heading = totalsHeading(scope, { uniqueCount: uniqueRows.length, rowCount: rows.length, versionsMixed }, closedTotal);
  const display = buildTotalsDisplay(pageSummary);

  const allClosed = buildAllClosedDisplay(summary, versionId, ruler);

  return (
    <div data-testid="lab-totals-card" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-medium text-fg">{heading}</p>
        <div className="flex items-center gap-2">
          <ScopeSwitch scope={scope} onChange={setScope} />
          {scope === "page" && (
            <Button type="button" variant="ghost" size="sm" aria-expanded={expanded} onClick={() => setExpanded((v) => !v)}>
              {expanded ? "Menos detalhes" : "Mais detalhes"}
            </Button>
          )}
        </div>
      </div>
      <SiblingVersionsNote scope={scope} versionsMixed={versionsMixed} />

      {scope === "page" ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label="Operações" value={String(pageSummary.total)} />
          <Stat
            label="Com lucro / prejuízo"
            value={`${pageSummary.withProfit} / ${pageSummary.withLoss}`}
            colorClass={pageSummary.withProfit > 0 || pageSummary.withLoss > 0 ? "text-fg" : undefined}
          />
          <Stat label="Taxa de acerto" value={display.winRateText} />
          <Stat
            label="Resultado acumulado"
            value={display.resultUsdtText}
            sub={display.resultBrlText}
            colorClass={moneyColor(pageSummary.resultUsdt.value)}
          />
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4" title={MONEY_TOOLTIP}>
          <Stat label="Operações concluídas" value={formatCount(closedTotal)} />
          <Stat label="Com lucro / prejuízo" value="—" sub={reasonLabel("not_aggregable_across_versions")} />
          <Stat label="Taxa de acerto" value={allClosed.winRateText} />
          <Stat label="Resultado acumulado" value={allClosed.resultText} sub={allClosed.resultBrlText} colorClass={allClosed.resultColor} />
        </div>
      )}

      {scope === "page" && expanded && (
        <>
          <div data-testid="lab-totals-more" className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label="Concluídas" value={String(pageSummary.completed)} />
            <Stat label="Pendentes" value={String(pageSummary.pending)} />
            <Stat label="Sem entrada" value={String(pageSummary.noEntry)} />
            <Stat label="Censuradas" value={String(pageSummary.censored)} />
          </div>
          <div title={MONEY_TOOLTIP} className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label="Média com lucro (desta página)" value={display.avgProfitText} colorClass={pageSummary.avgProfitUsdt.value !== null ? "text-green" : undefined} />
            <Stat label="Média com prejuízo (desta página)" value={display.avgLossText} colorClass={pageSummary.avgLossUsdt.value !== null ? "text-red" : undefined} />
            <Stat
              label="Melhor operação (desta página)"
              value={display.bestText}
              sub={display.bestSub}
              colorClass={pageSummary.best ? "text-green" : undefined}
            />
            <Stat
              label="Pior operação (desta página)"
              value={display.worstText}
              sub={display.worstSub}
              colorClass={pageSummary.worst ? "text-red" : undefined}
            />
          </div>
        </>
      )}
    </div>
  );
}
