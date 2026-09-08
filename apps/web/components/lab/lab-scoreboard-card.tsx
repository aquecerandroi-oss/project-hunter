"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { LabMaturityBar } from "@/components/lab/lab-maturity-bar";
import { LabVerdictBadge } from "@/components/lab/lab-verdict-badge";
import { buildScoreboardCardDisplay, VERDICT_RULE_TEXT } from "@/components/lab/lab-scoreboard";
import { MONEY_TOOLTIP, type MoneyRuler } from "@/components/lab/lab-money";
import { purposeLabel } from "@/components/lab/lab-strategy-cell";
import type { ScoreboardRowOut } from "@/lib/api/lab-types";

const STATUS_VARIANT: Record<string, "gold" | "default" | "outline"> = {
  active: "gold",
  deprecated: "default",
  draft: "outline",
};

function MoneyStat({ label, usdtText, brlText, colorClass }: { label: string; usdtText: string; brlText: string; colorClass: string }) {
  return (
    <div className="rounded-md border border-border p-3" title={MONEY_TOOLTIP}>
      <p className="text-xs font-medium uppercase text-fg-muted">{label} (simulado)</p>
      <p className={`mt-1 font-mono text-lg tabular-nums ${colorClass}`}>{usdtText}</p>
      <p className="text-xs text-fg-muted">{brlText}</p>
    </div>
  );
}

function ResearchStat({ label, value, colorClass, detail }: { label: string; value: string; colorClass?: string | undefined; detail?: string | undefined }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs text-fg-muted">{label}</span>
      <span className={`font-mono text-sm tabular-nums ${colorClass ?? "text-fg"}`}>{value}</span>
      {detail && <span className="text-[11px] text-fg-subtle">{detail}</span>}
    </div>
  );
}

export interface LabScoreboardCardProps {
  row: ScoreboardRowOut;
  ruler: MoneyRuler;
}

/**
 * One Placar card (brief T3.18 item 3): identity/status/since -> the verdict
 * as the dominant element next to its maturity bar -> money through the
 * T3.17 ruler (always visible) -> the research units behind the existing
 * "Detalhes de pesquisa" toggle. All display strings/colours come from
 * `buildScoreboardCardDisplay` (kept out of this JSX, T3.17b's own lesson on
 * the lint config's cyclomatic-complexity budget).
 */
export function LabScoreboardCard({ row, ruler }: LabScoreboardCardProps) {
  const [showResearch, setShowResearch] = useState(false);
  const display = buildScoreboardCardDisplay(row, ruler);
  const v = row.version;

  return (
    <div data-testid="lab-scoreboard-card" className="rounded-lg border border-border bg-bg-elevated p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-sm font-semibold text-fg">
          {v.strategy_key}/{v.version}
        </span>
        <Badge variant={v.purpose === "paper" ? "info" : "outline"} className="px-1.5 py-0 text-[10px]">
          {purposeLabel(v.purpose)}
        </Badge>
        <Badge variant={STATUS_VARIANT[v.status] ?? "outline"}>{display.statusLabel}</Badge>
        <span className="text-xs text-fg-subtle">{display.sinceText}</span>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-4">
        <LabVerdictBadge verdict={row.verdict} />
        <LabMaturityBar maturity={row.maturity} />
      </div>

      {display.noEvaluableReason !== null ? (
        <p className="mt-3 text-sm text-fg-muted">{display.noEvaluableReason}</p>
      ) : (
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <MoneyStat label="Resultado acumulado" usdtText={display.cumulativeUsdtText} brlText={display.cumulativeBrlText} colorClass={display.cumulativeUsdtColor} />
          <MoneyStat label="Média por operação" usdtText={display.avgUsdtText} brlText={display.avgBrlText} colorClass={display.avgUsdtColor} />
        </div>
      )}

      <Button
        type="button"
        variant="outline"
        size="sm"
        className="mt-3"
        aria-pressed={showResearch}
        onClick={() => setShowResearch((v2) => !v2)}
      >
        {showResearch ? "Ocultar detalhes de pesquisa" : "Detalhes de pesquisa"}
      </Button>

      {showResearch && (
        <div data-testid="lab-scoreboard-research" className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-5">
          <ResearchStat label="Taxa de alvo (toques resolvidos)" value={display.hitRateText} colorClass={display.hitRateIsValue ? undefined : "text-fg-muted"} />
          <ResearchStat label="Expectancy" value={display.expectancyText} colorClass={display.expectancyColor} />
          <ResearchStat label="Profit factor" value={display.pfText} colorClass={display.pfIsValue ? undefined : "text-fg-muted"} detail={display.pfDetail} />
          <ResearchStat label="Pior sequência" value={display.worstStreakText} />
          <ResearchStat label="Máx. drawdown" value={display.maxDrawdownText} />
        </div>
      )}

      <p className="mt-3 text-[11px] text-fg-subtle">{VERDICT_RULE_TEXT}</p>
    </div>
  );
}
