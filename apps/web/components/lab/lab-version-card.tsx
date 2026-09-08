import { TooltipProvider } from "@/components/ui/tooltip";
import { Badge } from "@/components/ui/badge";
import { reasonLabel, formatSumOfRDetail } from "@/components/lab/lab-format";
import { LabFunnel } from "@/components/lab/lab-funnel";
import { LabMaturityBadge } from "@/components/lab/lab-maturity-badge";
import { METRIC_DEFS } from "@/components/lab/lab-metric-defs";
import { LabMetricItem } from "@/components/lab/lab-metric-item";
import { LabRExFunding } from "@/components/lab/lab-r-ex-funding";
import { formatAssumedCosts } from "@/components/lab/lab-costs";
import { purposeLabel, statusLabel } from "@/components/lab/labels";
import type { VersionSummaryOut } from "@/lib/api/lab-types";

export interface LabVersionCardProps {
  version: VersionSummaryOut;
  /** Id + label of the version this one was superseded by, when it resolves to a version also rendered in this list (best-effort, contract-S3-lab.md). */
  supersededBy: { id: string; label: string } | null;
  /** `true` only when `?version=` in the URL points at this card (brief T3.24b item [4]) -- every other card renders collapsed. */
  openByDefault: boolean;
}

const STATUS_VARIANT: Record<VersionSummaryOut["status"], "gold" | "default" | "outline"> = {
  active: "gold",
  deprecated: "default",
  draft: "outline",
};

/** "hunter_core.strategies.momentum_v1@sha256:c012f75c..." -> the first 7 chars of the hash (brief T3.24b item [4]), full string kept in `title`. Falls back to the whole `code_ref` when it carries no `sha256:` marker. */
function shortCodeRef(codeRef: string): { short: string; full: string } {
  const marker = "sha256:";
  const at = codeRef.indexOf(marker);
  const hash = at >= 0 ? codeRef.slice(at + marker.length) : codeRef;
  return { short: hash.slice(0, 7), full: codeRef };
}

/**
 * One `strategy_version` card (brief S3b, collapsed by T3.24b item [4] into
 * a `<details>`): the `<summary>` carries only identity/status/purpose/
 * maturity/superseded-by -- one line, no JS needed to open/close (native
 * `<details>`). The body -- funnel, the five named metrics, the two
 * ALWAYS-visible "não aplicável" lines for portfolio PnL/drawdown (own
 * paragraph, not a badge stuck on the nearest metric, so it never reads as
 * qualifying that metric), `r_ex_funding` as its own block, coverage/assumed
 * costs -- only renders once opened.
 */
export function LabVersionCard({ version, supersededBy, openByDefault }: LabVersionCardProps) {
  const m = version.metrics;
  const codeRef = version.code_ref ? shortCodeRef(version.code_ref) : null;

  return (
    <TooltipProvider delayDuration={200}>
      <details id={`version-${version.strategy_version_id}`} open={openByDefault} className="rounded-lg border border-border bg-bg-elevated p-4">
        <summary className="flex cursor-pointer list-none flex-wrap items-center gap-2">
          <Badge variant={STATUS_VARIANT[version.status]}>{statusLabel(version.status)}</Badge>
          <span className="font-mono text-sm font-semibold text-fg">
            {version.strategy_key} / {version.version}
          </span>
          {/* strategy_versions.purpose (T3.15e, review-T3.15-risk.md item 5): the
              chip that tells a research-only row (never spends the wallet) apart
              from the paper coorte (the one that does) -- same label as the
              signals table's LabStrategyCell. */}
          <Badge variant={version.purpose === "paper" ? "info" : "outline"} className="px-1.5 py-0 text-[11px]">
            {purposeLabel(version.purpose)}
          </Badge>
          <LabMaturityBadge maturity={version.maturity} compact />
          {supersededBy && (
            <a
              href={`#version-${supersededBy.id}`}
              className="text-xs text-fg-muted underline underline-offset-2 hover:text-gold"
            >
              substituída por {supersededBy.label}
            </a>
          )}
        </summary>

        <div className="mt-3">
          {codeRef && (
            <p className="mb-3 text-[11px] text-fg-subtle" title={codeRef.full}>
              Código: {codeRef.short}
            </p>
          )}

          <LabFunnel counts={version.counts} />

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
              detail={formatSumOfRDetail(m.sum_of_hypothetical_r.count, m.sum_of_hypothetical_r.ordered_by)}
            />
          </div>

          {/* Astra's S3b review: own paragraph, not a badge next to the nearest
              financial metric -- proximity there could make "não aplicável"
              read as qualifying the expectancy or the R sum instead of stating
              a fact about the product (there is no portfolio in Shadow Lab). */}
          <p className="mt-4 text-xs text-fg-muted">PnL de carteira: {reasonLabel(version.portfolio_pnl_reason)}</p>
          <p className="text-xs text-fg-muted">Drawdown de carteira: {reasonLabel(version.portfolio_max_drawdown_reason)}</p>

          <div className="mt-4">
            <LabRExFunding block={version.r_ex_funding} />
          </div>

          <p className="mt-3 text-[11px] text-fg-subtle">
            {`cobertura: ${version.coverage.markets_with_signals} mercados com sinal, ${version.coverage.distinct_days} dias distintos -- ${formatAssumedCosts(version.coverage.assumed_costs)}`}
          </p>
        </div>
      </details>
    </TooltipProvider>
  );
}
