/**
 * `/system`'s "Latência" block vocabulary (DESIGN.md §2 "sem backstage na
 * copy" -- enum values never reach the screen raw: `ingest`/`critical`
 * mean nothing to Everton). `hop` travels as plain `string` in
 * `LatencyHopOut` (no literal union in the OpenAPI contract -- see
 * `hunter_api/schemas/latency.py`), so `LATENCY_HOP_VALUES` below -- not the
 * TS type -- is what `tests/latency-labels.test.ts` iterates for
 * exhaustiveness; an unrecognized hop still renders (falls back to itself)
 * rather than disappearing, same convention as `components/system/labels.ts`.
 *
 * Row names follow the brief's Portuguese phrasing (T3.79) as closely as the
 * actual five hops allow: the brief names four hop labels plus "ponta a
 * ponta" for what the frozen contract publishes as five hops
 * (`ingest`/`flush`/`decision`/`admission`/`fill`) plus `end_to_end` --
 * `services/latency.py`'s own docstring groups `ingest`+`flush` under one
 * family ("exchange event -> candle on our stream"), so both get a label in
 * that family instead of collapsing two SLOs with independent p50/p95/status
 * into one row.
 */
import type { LatencySloStatus } from "@/lib/api/latency-types";

export const LATENCY_HOP_VALUES = ["ingest", "flush", "decision", "admission", "fill", "end_to_end"] as const;
export type LatencyHopValue = (typeof LATENCY_HOP_VALUES)[number];

const HOP_LABEL: Record<LatencyHopValue, string> = {
  ingest: "Evento da Binance → recebido",
  flush: "Vela fechada → publicada",
  decision: "Vela → decisão",
  admission: "Decisão → admissão",
  fill: "Admissão → fill",
  end_to_end: "Ponta a ponta",
};

export function latencyHopLabel(hop: string): string {
  return HOP_LABEL[hop as LatencyHopValue] ?? hop;
}

/**
 * The API's `LatencyHopOut` carries no per-hop `reason` field (only
 * `status`) -- unlike `hunter_core.latency.LagMeasurement`, which does, that
 * detail never crosses into the published contract. This names, per hop
 * family, which worker's heartbeat is expected to eventually carry the
 * field, matching `hunter_api/services/latency.py`'s own module docstring --
 * an honest, generic reason, never a fabricated specific cause the frontend
 * cannot actually observe.
 */
const HOP_UNKNOWN_REASON: Record<LatencyHopValue, string> = {
  ingest: "o heartbeat do market-worker ainda não reporta este dado",
  flush: "o heartbeat do market-worker ainda não reporta este dado",
  decision: "o heartbeat do strategy-worker ainda não reporta este dado",
  admission: "o heartbeat do execution-worker ainda não reporta este dado",
  fill: "o heartbeat do execution-worker ainda não reporta este dado",
  end_to_end: "nem todos os trechos acima têm leitura",
};

export function latencyUnknownReason(hop: string): string {
  return HOP_UNKNOWN_REASON[hop as LatencyHopValue] ?? "sem leitura ainda";
}

const STATUS_LABEL: Record<LatencySloStatus, string> = {
  ok: "OK",
  warn: "Atenção",
  critical: "Crítico",
  unknown: "Sem medição",
};

export function latencyStatusLabel(status: LatencySloStatus): string {
  return STATUS_LABEL[status];
}

const STATUS_BADGE_VARIANT: Record<LatencySloStatus, "positive" | "warning" | "negative" | "default"> = {
  ok: "positive",
  warn: "warning",
  critical: "negative",
  unknown: "default",
};

export function latencyStatusBadgeVariant(status: LatencySloStatus): "positive" | "warning" | "negative" | "default" {
  return STATUS_BADGE_VARIANT[status];
}

/** Seconds -> "0.09s"/"180.00s" -- two decimals always (tabular-nums, docs/DESIGN.md §2), never truncated to hide a sub-second reading against the tightest budget (0.5s, `ingest`/`flush`). */
export function formatLatencySeconds(value: number): string {
  return `${value.toFixed(2)}s`;
}
