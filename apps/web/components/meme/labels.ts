/**
 * Meme Radar vocabulary (DESIGN.md §2 "sem backstage na copy" -- enum values
 * never reach the screen raw: `curve`/`no_trade_feed` mean nothing to
 * Everton). `Record<Enum, string>` makes the compiler itself enforce
 * completeness for every literal union the OpenAPI contract publishes
 * (`lib/api/meme-types.ts`); `tests/meme-labels.test.ts` iterates the same
 * value arrays for a second, explicit exhaustiveness check (the convention
 * `components/system/latency-labels.ts` already established).
 */
import type { MemeGapStream, MemeNullReason, MemeSource, MemeToken, MemeTokenState } from "@/lib/api/meme-types";

export const MEME_TOKEN_STATES: readonly MemeTokenState[] = ["curve", "completed", "migrated"];

const TOKEN_STATE_LABEL: Record<MemeTokenState, string> = {
  curve: "Na curva",
  // T4.2d: `completed_at` is the earliest of the four completion signals (0024),
  // never the REST boolean alone -- the filter and this label follow it.
  completed: "Concluída (sinal mais antigo)",
  migrated: "Migrado (PumpSwap)",
};

export function memeTokenStateLabel(state: MemeTokenState): string {
  return TOKEN_STATE_LABEL[state];
}

export const MEME_SOURCES: readonly MemeSource[] = [
  "pumpportal_ws",
  "pumpfun_rest",
  "solana_rpc",
  "trenches_ws",
];

const SOURCE_LABEL: Record<MemeSource, string> = {
  pumpportal_ws: "PumpPortal (WS)",
  pumpfun_rest: "pump.fun (REST)",
  solana_rpc: "Solana RPC",
  // T4.2c: the site's own screener feed (advanced-indexer /ws/trenches).
  trenches_ws: "boards do site (WS)",
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
  "no_sells",
  "out_of_range",
];

const NULL_REASON_LABEL: Record<MemeNullReason, string> = {
  no_trade_feed: "sem fita de negociações neste minuto",
  no_holders_reader: "sem leitor de holders ainda",
  denominator_unknown: "denominador da curva desconhecido",
  not_polled: "ainda não consultado nesta janela",
  rate_limited: "limite de requisições atingido",
  insufficient_coverage: "cobertura insuficiente no minuto",
  unsupported_quote: "cotação fora do padrão suportado",
  // T4.2c: a ratio with no sells in the minute has no value, and this says why.
  no_sells: "sem vendas no minuto (razão indefinida)",
  // A share above 100 % from the site's board in a coin's first minute is not stored.
  out_of_range: "valor da fonte fora da faixa possível (não gravado)",
};

export function memeNullReasonLabel(reason: MemeNullReason): string {
  return NULL_REASON_LABEL[reason];
}

/** "sem medição: <motivo>" -- the exact null-with-reason phrasing the brief asks for on the features table. */
export function memeNullReasonText(reason: MemeNullReason | null | undefined): string {
  if (!reason) return "sem medição: motivo não informado";
  return `sem medição: ${memeNullReasonLabel(reason)}`;
}

// T4.2d: the four completion signals of `meme_tokens` (migration 0024). "REST
// diz completa" is a REST photo, not a graduation -- the plantão measured 77 of
// 140 "complete" coins with a zero reserve -- so each signal keeps its own name
// and the screen shows disagreement instead of folding them into one word.
export type CompletionSignalKey = "rest_complete" | "curve_filled" | "graduated_board" | "pool_created";

export const COMPLETION_SIGNAL_KEYS: readonly CompletionSignalKey[] = ["rest_complete", "curve_filled", "graduated_board", "pool_created"];

const COMPLETION_SIGNAL_LABEL: Record<CompletionSignalKey, string> = {
  rest_complete: "REST diz completa",
  curve_filled: "curva cheia (≥ 85 SOL)",
  graduated_board: "no board graduated",
  pool_created: "pool criada",
};

export function memeCompletionSignalLabel(key: CompletionSignalKey): string {
  return COMPLETION_SIGNAL_LABEL[key];
}

export type MemePoolSource = NonNullable<MemeToken["pool_created_source"]>;

export const MEME_POOL_SOURCES: readonly MemePoolSource[] = ["pumpportal_ws", "trenches_ws", "indexer_rest:/boards", "indexer_rest:/in-memory-coin"];

const POOL_SOURCE_LABEL: Record<MemePoolSource, string> = {
  pumpportal_ws: "PumpPortal (evento migrate)",
  trenches_ws: "boards do site (WS)",
  "indexer_rest:/boards": "boards do site (REST)",
  "indexer_rest:/in-memory-coin": "leitura de risco do site",
};

export function memePoolSourceLabel(source: MemePoolSource): string {
  return POOL_SOURCE_LABEL[source];
}

export type MemeDenominatorSource = MemeToken["progress_denominator_source"];

export const MEME_DENOMINATOR_SOURCES: readonly MemeDenominatorSource[] = ["observed_virgin", "global_params", "mayhem_state", "unknown"];

const DENOMINATOR_SOURCE_LABEL: Record<MemeDenominatorSource, string> = {
  observed_virgin: "observado na curva virgem",
  global_params: "parâmetros globais do programa",
  // T4.2e: a Mayhem curve keeps the registry reserve; the agent's extra billion lives in `MayhemState`.
  mayhem_state: "registro + conta MayhemState (curva Mayhem)",
  unknown: "desconhecido",
};

export function memeDenominatorSourceLabel(source: MemeDenominatorSource): string {
  return DENOMINATOR_SOURCE_LABEL[source];
}
