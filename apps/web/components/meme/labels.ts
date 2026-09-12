/**
 * Meme Radar vocabulary (DESIGN.md §2 "sem backstage na copy" -- enum values
 * never reach the screen raw: `curve`/`no_trade_feed` mean nothing to
 * Everton). `Record<Enum, string>` makes the compiler itself enforce
 * completeness for every literal union the OpenAPI contract publishes
 * (`lib/api/meme-types.ts`); `tests/meme-labels.test.ts` iterates the same
 * value arrays for a second, explicit exhaustiveness check (the convention
 * `components/system/latency-labels.ts` already established).
 */
import type { MemeGapStream, MemeNullReason, MemeRadarStatus, MemeSource, MemeSourceStatus, MemeToken, MemeTokenState } from "@/lib/api/meme-types";

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

// T4.3b: the feeds the worker's heartbeat reports (`services/meme_sources.py`
// `SOURCE_NAMES`). `name` is a plain string in the contract -- a feed added
// upstream before this map learns it still gets a readable name (underscores
// to spaces) instead of throwing or hiding the source. T4.2g added
// `swap_api_activity`, the batch tape (POST market-activity/batch) that fills
// the minute when the per-mint tape did not cover it -- same swap-api budget,
// its own line here so the two tapes never read as one.
export const MEME_FEED_SOURCES: readonly string[] = ["pumpportal_ws", "pumpfun_rest", "solana_rpc", "trenches_ws", "swap_api", "indexer_risk", "swap_api_activity"];

const FEED_SOURCE_LABEL: Record<string, string> = {
  pumpportal_ws: "PumpPortal (WS)",
  pumpfun_rest: "pump.fun (REST)",
  solana_rpc: "Solana RPC",
  trenches_ws: "boards do site (WS)",
  swap_api: "fita por mint (swap-api)",
  indexer_risk: "risco do site (indexer)",
  swap_api_activity: "fita por lote (swap-api)",
};

export function memeFeedSourceLabel(name: string): string {
  return FEED_SOURCE_LABEL[name] ?? name.replace(/_/g, " ");
}

export const MEME_RADAR_STATUSES: readonly MemeRadarStatus[] = ["alive", "stale", "never", "heartbeat_missing", "redis_unavailable"];

const RADAR_STATUS_LABEL: Record<MemeRadarStatus, string> = {
  alive: "radar vivo",
  stale: "radar parado",
  never: "o worker subiu, mas o radar nunca escreveu seus campos",
  heartbeat_missing: "sem heartbeat do worker",
  redis_unavailable: "Redis indisponível",
};

export function memeRadarStatusLabel(status: MemeRadarStatus): string {
  return RADAR_STATUS_LABEL[status];
}

export const MEME_SOURCE_STATUSES: readonly MemeSourceStatus[] = ["connected", "disconnected", "ok", "erroring", "disabled", "unknown"];

const SOURCE_STATUS_LABEL: Record<MemeSourceStatus, string> = {
  connected: "conectada",
  disconnected: "desconectada",
  ok: "em dia",
  erroring: "com erro",
  disabled: "desligada",
  unknown: "sem leitura",
};

export function memeSourceStatusLabel(status: MemeSourceStatus): string {
  return SOURCE_STATUS_LABEL[status];
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
  "no_sol_quote",
];

const NULL_REASON_LABEL: Record<MemeNullReason, string> = {
  no_trade_feed: "sem fita",
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
  // T4.2g: the batch tape speaks USD; without a SOL/USD quote under 5 min the SOL figures are not derived.
  no_sol_quote: "sem cotação SOL/USD no minuto",
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

// T4.10b: the trend-line columns of `meme_features_v3` (brief T4.10
// §Contrato). The vocabularies are typed here, not off the generated
// contract, because the screen is built against the brief while the backend
// lands in parallel; `Record<Enum, string>` still makes the compiler check the
// map, and the label functions accept any string so a value the vocabulary
// does not know yet renders as readable text instead of crashing the build
// or the page (three deploys broke on 2026-09-12 for a missing label).
export type MemeLineReason = "too_few_points" | "no_snapshot" | "flat" | "out_of_range";

export const MEME_LINE_REASONS: readonly MemeLineReason[] = ["too_few_points", "no_snapshot", "flat", "out_of_range"];

const LINE_REASON_LABEL: Record<MemeLineReason, string> = {
  too_few_points: "menos de 5 fotografias na janela",
  no_snapshot: "sem fotografia da curva na janela",
  flat: "sem dois fundos distintos (curva plana)",
  out_of_range: "valor fora da faixa possível (não gravado)",
};

function unknownReason(reason: string): string {
  return `motivo não previsto (${reason.replace(/_/g, " ")})`;
}

export function memeLineReasonLabel(reason: string): string {
  return (LINE_REASON_LABEL as Record<string, string>)[reason] ?? unknownReason(reason);
}

/** The columns exist but are absent from the payload -- an older `features_version`, never a "no line" verdict. */
export const MEME_LINE_NO_READING = "linha: sem leitura";

/** "linha ainda não traçável: <motivo>" -- the exact phrasing the brief asks for when `line_reason` is present. */
export function memeLineUntraceableText(reason: string | null | undefined): string {
  if (!reason) return "linha ainda não traçável: motivo não informado";
  return `linha ainda não traçável: ${memeLineReasonLabel(reason)}`;
}

export type MemeHypeReason = "no_tape_no_board" | "partial";

export const MEME_HYPE_REASONS: readonly MemeHypeReason[] = ["no_tape_no_board", "partial"];

const HYPE_REASON_LABEL: Record<MemeHypeReason, string> = {
  no_tape_no_board: "sem fita e sem board no minuto",
  // `partial` rides beside a score computed from one of the two sources.
  partial: "só uma das duas fontes (fita ou board)",
};

export function memeHypeReasonLabel(reason: string): string {
  return (HYPE_REASON_LABEL as Record<string, string>)[reason] ?? unknownReason(reason);
}

export const MEME_HYPE_NO_READING = "hype: sem leitura";

export function memeHypeMissingText(reason: string | null | undefined): string {
  if (!reason) return "sem hype: motivo não informado";
  return `sem hype: ${memeHypeReasonLabel(reason)}`;
}
