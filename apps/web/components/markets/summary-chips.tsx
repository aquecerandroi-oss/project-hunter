import { Badge } from "@/components/ui/badge";
import type { MarketsSummary } from "@/lib/api/types";

export interface SummaryChipsProps {
  summary: MarketsSummary;
}

/** Header counts straight from the API's `summary` -- never recomputed from the (possibly capped) page of rows. */
export function SummaryChips({ summary }: SummaryChipsProps) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <Badge variant="outline">{summary.markets_total} mercados</Badge>
      <Badge variant="gold">{summary.markets_monitored} monitorados</Badge>
      <Badge variant="positive">{summary.markets_ok} ok</Badge>
      <Badge variant="warning">{summary.markets_stale} atrasados</Badge>
      <Badge variant="negative">{summary.markets_degraded} degradados</Badge>
      <Badge variant="default">{summary.markets_unavailable} sem dado</Badge>
    </div>
  );
}
