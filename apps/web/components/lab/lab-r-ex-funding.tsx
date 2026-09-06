"use client";

import { LabMetricItem } from "@/components/lab/lab-metric-item";
import { METRIC_DEFS } from "@/components/lab/lab-metric-defs";
import type { RExFundingBlock } from "@/lib/api/lab-types";

export interface LabRExFundingProps {
  block: RExFundingBlock;
}

/**
 * `r_ex_funding` as its OWN block (brief S3b), never merged into the main
 * five metrics: it is the same population but with `meta.r_ex_funding` in
 * place of `r_multiple` -- coverage that can differ (>=) from `r_net`'s,
 * spelled out in `coverage` below rather than left implicit.
 */
export function LabRExFunding({ block }: LabRExFundingProps) {
  return (
    <div className="rounded-md border border-border bg-bg-overlay/50 p-3">
      <p className="mb-2 text-xs font-semibold text-fg-muted">r_ex_funding (mesma população, sem funding)</p>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <LabMetricItem
          label={METRIC_DEFS.net_profit_rate.label}
          definition={METRIC_DEFS.net_profit_rate.definition}
          value={block.net_profit_rate.value}
          reason={block.net_profit_rate.reason}
        />
        <LabMetricItem
          label={METRIC_DEFS.hypothetical_net_expectancy_r.label}
          definition={METRIC_DEFS.hypothetical_net_expectancy_r.definition}
          value={block.hypothetical_net_expectancy_r.value}
          reason={block.hypothetical_net_expectancy_r.reason}
          suffix="R"
        />
        <LabMetricItem
          label={METRIC_DEFS.profit_factor.label}
          definition={METRIC_DEFS.profit_factor.definition}
          value={block.profit_factor.value}
          reason={block.profit_factor.reason}
          detail={`+${block.profit_factor.sum_positive} / -${block.profit_factor.sum_negative_abs} (n=${block.profit_factor.sample_size})`}
        />
        <LabMetricItem
          label={METRIC_DEFS.sum_of_hypothetical_r.label}
          definition={METRIC_DEFS.sum_of_hypothetical_r.definition}
          value={block.sum_of_hypothetical_r.value}
          reason={block.sum_of_hypothetical_r.reason}
          suffix="R"
          detail={`n=${block.sum_of_hypothetical_r.count}, ordenada por ${block.sum_of_hypothetical_r.ordered_by}`}
        />
      </div>
      <p className="mt-2 text-[11px] text-fg-subtle">
        {`cobertura: ${block.coverage.evaluable_outcomes} outcomes avaliáveis, ${block.coverage.r_net_evaluable_outcomes} também com r_multiple`}
      </p>
    </div>
  );
}
