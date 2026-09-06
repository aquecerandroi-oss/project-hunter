import { Badge } from "@/components/ui/badge";

export interface RadarAnomalySummary {
  type: string;
}

const WINDOW_LABEL = "30d, ativas";

/**
 * Radar's "anomalias ativas" column (brief line 9). `RadarItemOut` itself
 * carries no anomaly data -- this is built from
 * `lib/api/anomalies-types.ts::buildAnomaliesAggregate`, grouped by
 * `market_id`. Two honesty limits, named explicitly in the cell itself
 * (not only in a code comment, Astra's T2.7 diff review, must-fix 3) rather
 * than presented as a complete "active now" count: the 30-day window can
 * miss a genuinely older `active + unknown` anomaly, and a truncated
 * aggregate page can leave a market's real anomaly out of `byMarket`
 * entirely -- so "nenhuma" always carries the truncation caveat too, never
 * silently claiming a clean market that the aggregate simply didn't cover.
 */
export function AnomalyCountCell({
  anomalies,
  unavailable,
  truncated,
}: {
  anomalies: RadarAnomalySummary[] | undefined;
  unavailable: boolean;
  truncated: boolean;
}) {
  if (unavailable) return <span className="text-xs text-fg-muted">sem verificação</span>;

  if (!anomalies || anomalies.length === 0) {
    return (
      <div className="flex flex-col gap-1">
        <span className="text-xs text-fg-subtle">nenhuma ({WINDOW_LABEL})</span>
        {truncated && <span className="text-[11px] text-fg-subtle">lista truncada — este mercado pode não ter sido coberto</span>}
      </div>
    );
  }

  const types = [...new Set(anomalies.map((a) => a.type))];
  return (
    <div className="flex flex-col gap-1">
      <div className="flex flex-wrap items-center gap-1">
        <Badge variant="warning">{anomalies.length}</Badge>
        <span className="text-xs text-fg-muted">
          {types.join(", ")} ({WINDOW_LABEL})
        </span>
      </div>
      {truncated && <span className="text-[11px] text-fg-subtle">lista truncada — a contagem pode estar subestimada</span>}
    </div>
  );
}
