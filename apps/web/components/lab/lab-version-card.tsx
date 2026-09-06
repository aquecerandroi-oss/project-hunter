"use client";

import { TooltipProvider } from "@/components/ui/tooltip";
import { Badge } from "@/components/ui/badge";
import { LabFunnel } from "@/components/lab/lab-funnel";
import { LabMaturityBadge } from "@/components/lab/lab-maturity-badge";
import { METRIC_DEFS } from "@/components/lab/lab-metric-defs";
import { LabMetricItem } from "@/components/lab/lab-metric-item";
import { LabRExFunding } from "@/components/lab/lab-r-ex-funding";
import { formatAssumedCosts } from "@/components/lab/lab-costs";
import type { VersionSummaryOut } from "@/lib/api/lab-types";

export interface LabVersionCardProps {
  version: VersionSummaryOut;
  /** Id + label of the version this one was superseded by, when it resolves to a version also rendered in this list (best-effort, contract-S3-lab.md). */
  supersededBy: { id: string; label: string } | null;
}

const STATUS_VARIANT: Record<VersionSummaryOut["status"], "gold" | "default" | "outline"> = {
  active: "gold",
  deprecated: "default",
  draft: "outline",
};

/**
 * One `strategy_version` card (brief S3b). Hierarchy inside the card
 * follows Astra's S3b review: identity/status -> maturity (next to the
 * funnel, the sample that qualifies every number below) -> the five named
 * metrics -> two ALWAYS-visible "não aplicável" lines for portfolio PnL/
 * drawdown (own paragraph, not a badge stuck on the nearest metric, so it
 * never reads as qualifying that metric) -> `r_ex_funding` as its own block
 * -> coverage/assumed costs, per-version (never globalized from the first
 * version in view).
 */
export function LabVersionCard({ version, supersededBy }: LabVersionCardProps) {
  const m = version.metrics;
  return (
    <TooltipProvider delayDuration={200}>
      <div id={`version-${version.strategy_version_id}`} className="rounded-lg border border-border bg-bg-elevated p-4">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={STATUS_VARIANT[version.status]}>{version.status}</Badge>
          <span className="font-mono text-sm font-semibold text-fg">
            {version.strategy_key} / {version.version}
          </span>
          {supersededBy && (
            <a
              href={`#version-${supersededBy.id}`}
              className="text-xs text-fg-muted underline underline-offset-2 hover:text-gold"
            >
              substituída por {supersededBy.label}
            </a>
          )}
        </div>
        {version.code_ref && <p className="mt-1 truncate text-[11px] text-fg-subtle">{version.code_ref}</p>}

        <div className="mt-3">
          <LabMaturityBadge maturity={version.maturity} />
        </div>

        <div className="mt-3">
          <LabFunnel counts={version.counts} />
        </div>

        <div data-testid="lab-main-metrics" className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-5">
          <LabMetricItem
            label={METRIC_DEFS.target_rate_among_resolved_touches.label}
            definition={METRIC_DEFS.target_rate_among_resolved_touches.definition}
            value={m.target_rate_among_resolved_touches.value}
            reason={m.target_rate_among_resolved_touches.reason}
          />
          <LabMetricItem
            label={METRIC_DEFS.net_profit_rate.label}
            definition={METRIC_DEFS.net_profit_rate.definition}
            value={m.net_profit_rate.value}
            reason={m.net_profit_rate.reason}
          />
          <LabMetricItem
            label={METRIC_DEFS.hypothetical_net_expectancy_r.label}
            definition={METRIC_DEFS.hypothetical_net_expectancy_r.definition}
            value={m.hypothetical_net_expectancy_r.value}
            reason={m.hypothetical_net_expectancy_r.reason}
            suffix="R"
          />
          <LabMetricItem
            label={METRIC_DEFS.profit_factor.label}
            definition={METRIC_DEFS.profit_factor.definition}
            value={m.profit_factor.value}
            reason={m.profit_factor.reason}
            detail={`+${m.profit_factor.sum_positive} / -${m.profit_factor.sum_negative_abs} (n=${m.profit_factor.sample_size})`}
          />
          <LabMetricItem
            label={METRIC_DEFS.sum_of_hypothetical_r.label}
            definition={METRIC_DEFS.sum_of_hypothetical_r.definition}
            value={m.sum_of_hypothetical_r.value}
            reason={m.sum_of_hypothetical_r.reason}
            suffix="R"
            detail={`n=${m.sum_of_hypothetical_r.count}, ordenada por ${m.sum_of_hypothetical_r.ordered_by}`}
          />
        </div>

        {/* Astra's S3b review: own paragraph, not a badge next to the nearest
            financial metric -- proximity there could make "não aplicável"
            read as qualifying the expectancy or the R sum instead of stating
            a fact about the product (there is no portfolio in Shadow Lab). */}
        <p className="mt-4 text-xs text-fg-muted">PnL de carteira: não aplicável ({version.portfolio_pnl_reason})</p>
        <p className="text-xs text-fg-muted">
          Drawdown de carteira: não aplicável ({version.portfolio_max_drawdown_reason})
        </p>

        <div className="mt-4">
          <LabRExFunding block={version.r_ex_funding} />
        </div>

        <p className="mt-3 text-[11px] text-fg-subtle">
          {`cobertura: ${version.coverage.markets_with_signals} mercados com sinal, ${version.coverage.distinct_days} dias distintos -- ${formatAssumedCosts(version.coverage.assumed_costs)}`}
        </p>
      </div>
    </TooltipProvider>
  );
}
