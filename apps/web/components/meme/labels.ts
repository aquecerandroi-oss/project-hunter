/**
 * Meme Radar vocabulary (DESIGN.md §2 "sem backstage na copy" -- enum values
 * never reach the screen raw: `curve`/`no_trade_feed` mean nothing to
 * Everton). `Record<Enum, string>` makes the compiler itself enforce
 * completeness for every literal union the OpenAPI contract publishes
 * (`lib/api/meme-types.ts`); `tests/meme-labels.test.ts` iterates the same
 * value arrays for a second, explicit exhaustiveness check (the convention
 * `components/system/latency-labels.ts` already established).
 */
import type { MemeGapStream, MemeNullReason, MemeSource, MemeTokenState } from "@/lib/api/meme-types";

export const MEME_TOKEN_STATES: readonly MemeTokenState[] = ["curve", "completed", "migrated"];

const TOKEN_STATE_LABEL: Record<MemeTokenState, string> = {
  curve: "Na curva",
  completed: "Concluiu a curva",
  migrated: "Migrado (PumpSwap)",
};

export function memeTokenStateLabel(state: MemeTokenState): string {
  return TOKEN_STATE_LABEL[state];
}

export const MEME_SOURCES: readonly MemeSource[] = ["pumpportal_ws", "pumpfun_rest", "solana_rpc"];

const SOURCE_LABEL: Record<MemeSource, string> = {
  pumpportal_ws: "PumpPortal (WS)",
  pumpfun_rest: "pump.fun (REST)",
  solana_rpc: "Solana RPC",
};

export function memeSourceLabel(source: MemeSource): string {
  return SOURCE_LABEL[source];
}

export const MEME_GAP_STREAMS: readonly MemeGapStream[] = ["pumpportal_ws", "curve_poll", "features_1m"];

const GAP_STREAM_LABEL: Record<MemeGapStream, string> = {
  pumpportal_ws: "conexão WS (PumpPortal)",
  curve_poll: "consulta da curva",
  features_1m: "cálculo de features",
};

export function memeGapStreamLabel(stream: MemeGapStream): string {
  return GAP_STREAM_LABEL[stream];
}

export const MEME_NULL_REASONS: readonly MemeNullReason[] = [
  "no_trade_feed",
  "no_holders_reader",
  "denominator_unknown",
  "not_polled",
  "rate_limited",
  "insufficient_coverage",
  "unsupported_quote",
];

const NULL_REASON_LABEL: Record<MemeNullReason, string> = {
  no_trade_feed: "sem feed de negociações (canal pago, não contratado)",
  no_holders_reader: "sem leitor de holders ainda",
  denominator_unknown: "denominador da curva desconhecido",
  not_polled: "ainda não consultado nesta janela",
  rate_limited: "limite de requisições atingido",
  insufficient_coverage: "cobertura insuficiente no minuto",
  unsupported_quote: "cotação fora do padrão suportado",
};

export function memeNullReasonLabel(reason: MemeNullReason): string {
  return NULL_REASON_LABEL[reason];
}

/** "sem medição: <motivo>" -- the exact null-with-reason phrasing the brief asks for on the features table. */
export function memeNullReasonText(reason: MemeNullReason | null | undefined): string {
  if (!reason) return "sem medição: motivo não informado";
  return `sem medição: ${memeNullReasonLabel(reason)}`;
}
