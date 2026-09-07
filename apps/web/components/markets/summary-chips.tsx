import { Badge } from "@/components/ui/badge";
import type { MarketsSummary } from "@/lib/api/types";

export interface SummaryChipsProps {
  summary: MarketsSummary;
}

/**
 * The collector's topology, or nothing (T2.5g). `collector_shards_expected` is
 * `null` whenever no market-worker is reporting a heartbeat, and a guessed "1
 * shard" would be exactly the invented number this project forbids.
 */
function ShardChip({ summary }: SummaryChipsProps) {
  const expected = summary.collector_shards_expected;
  const reporting = summary.collector_shards_reporting;
  if (expected === null || expected === undefined || reporting === null || reporting === undefined) return null;
  const complete = reporting >= expected;
  return (
    <Badge variant={complete ? "outline" : "warning"} title="Processos do coletor (market-worker) por trás destes mercados">
      {complete ? `${expected} shards, ` : `${reporting} de ${expected} shards, `}
      {summary.markets_monitored} mercados
    </Badge>
  );
}

/** Header counts straight from the API's `summary` -- never recomputed from the (possibly capped) page of rows. */
export function SummaryChips({ summary }: SummaryChipsProps) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <ShardChip summary={summary} />
      <Badge variant="outline">{summary.markets_total} mercados</Badge>
      <Badge variant="gold">{summary.markets_monitored} monitorados</Badge>
      <Badge variant="positive">{summary.markets_ok} ok</Badge>
      <Badge variant="warning">{summary.markets_stale} atrasados</Badge>
      <Badge variant="negative">{summary.markets_degraded} degradados</Badge>
      <Badge variant="default">{summary.markets_unavailable} sem dado</Badge>
    </div>
  );
}
