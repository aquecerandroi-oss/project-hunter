import { AlertTriangle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  formatLatencySeconds,
  latencyHopLabel,
  latencyStatusBadgeVariant,
  latencyStatusLabel,
  latencyUnknownReason,
} from "@/components/system/latency-labels";
import { SystemAsOf } from "@/components/system/system-as-of";
import type { LatencyHop, LatencyOut } from "@/lib/api/latency-types";

export interface LatencyPanelProps {
  /** `GET /api/v1/system/latency` (brief T3.79), already `.parse()`d server-side. */
  data: LatencyOut;
}

const UNAVAILABLE = "indisponível";

/** `null` -> "indisponível", never a fabricated `0s` -- only reachable when a hop's status is not `unknown` but one of its two numbers is still absent (should not happen per the API's own reservoir, kept honest anyway). */
function valueCell(value: number | null): string {
  return value === null ? UNAVAILABLE : formatLatencySeconds(value);
}

function LatencyRow({ hop, emphasize = false }: { hop: LatencyHop; emphasize?: boolean }) {
  const isCritical = hop.status === "critical";
  const isUnknown = hop.status === "unknown";
  const rowClassName = [
    "h-8 border-t",
    emphasize ? "border-border-strong font-medium" : "border-border",
    // Everton, 2026-09-10 ("quero tudo instantâneo"): a critical hop gets a
    // full-row tint, not only a badge -- a small colored pill in a busy
    // table is easy to miss, a tinted row is not.
    isCritical ? "bg-red-soft" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <tr className={rowClassName} data-testid={`latency-row-${hop.hop}`}>
      <td className="px-3 text-fg">{latencyHopLabel(hop.hop)}</td>
      {isUnknown ? (
        <td className="px-3 text-fg-muted" colSpan={2}>
          sem medição: {latencyUnknownReason(hop.hop)}
        </td>
      ) : (
        <>
          <td className={`px-3 text-right font-mono tabular-nums ${isCritical ? "font-semibold text-red" : "text-fg"}`}>
            {valueCell(hop.p50_s)}
          </td>
          <td className={`px-3 text-right font-mono tabular-nums ${isCritical ? "font-semibold text-red" : "text-fg"}`}>
            {valueCell(hop.p95_s)}
          </td>
        </>
      )}
      <td className="px-3 text-right font-mono tabular-nums text-fg-muted">
        {formatLatencySeconds(hop.target_p50_s)} / {formatLatencySeconds(hop.target_p95_s)}
      </td>
      <td className="px-3">
        <span className="inline-flex items-center gap-1.5">
          {isCritical ? <AlertTriangle aria-hidden="true" className="size-3.5 text-red" /> : null}
          <Badge variant={latencyStatusBadgeVariant(hop.status)}>{latencyStatusLabel(hop.status)}</Badge>
        </span>
      </td>
    </tr>
  );
}

/**
 * "Latência" (brief T3.79, Everton: "quero tudo instantâneo") -- the five
 * measured hops (`hunter_api/schemas/latency.py`) plus the derived "ponta a
 * ponta" summary, one row each. A `critical` row is tinted end to end
 * (background + bold red numbers + a warning icon next to its badge), not
 * only a colored pill -- the rule this screen exists to satisfy is that a
 * red hop cannot be scrolled past unnoticed. `unknown` never prints a number
 * (not even `0`/`--`): it names, per hop, which worker's heartbeat has not
 * reported this figure yet (`latencyUnknownReason`).
 */
export function LatencyPanel({ data }: LatencyPanelProps) {
  return (
    <section className="rounded-lg border border-border bg-bg-elevated p-4" data-testid="latency-panel">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-xs font-medium uppercase tracking-wide text-fg-muted">Latência</h2>
        <span className="text-xs text-fg-subtle">
          Consultado em <SystemAsOf iso={data.generated_at} />
        </span>
      </div>
      <div className="mt-3 overflow-x-auto rounded-md border border-border">
        <table className="w-full text-left text-[13px]">
          <thead className="bg-bg-overlay text-xs text-fg-muted">
            <tr>
              <th className="h-8 px-3 font-medium">Trecho</th>
              <th className="h-8 px-3 font-medium text-right">p50</th>
              <th className="h-8 px-3 font-medium text-right">p95</th>
              <th className="h-8 px-3 font-medium text-right">Alvo (p50 / p95)</th>
              <th className="h-8 px-3 font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {data.hops.map((hop) => (
              <LatencyRow key={hop.hop} hop={hop} />
            ))}
            <LatencyRow hop={data.end_to_end} emphasize />
          </tbody>
        </table>
      </div>
    </section>
  );
}
