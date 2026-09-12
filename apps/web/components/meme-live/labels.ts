/**
 * Real-executor vocabulary (DESIGN-5 "sem backstage na copy"): every enum
 * value from `apps/api/hunter_api/schemas/meme_live.py` gets a Portuguese
 * label here, `tests/meme-live-labels.test.ts` iterating the same arrays for
 * exhaustiveness (the `components/meme-desk/labels.ts` convention). The
 * check-named refusals (`first_refusal`/`last_refusal`/`blocked_exits`) live
 * in `refusal-labels.ts` -- a different, much larger vocabulary.
 */
import type { Problem } from "@hunter/shared-types";

import {
  type ExecutorStatus,
  type LiveOrderStatus,
  type LivePositionStatus,
  isExecutorStatus,
  isLiveOrderStatus,
  isLivePositionStatus,
} from "@/lib/api/meme-live-types";

const EXECUTOR_STATUS_LABEL: Record<ExecutorStatus, string> = {
  alive: "no ar",
  stalled: "parado — heartbeat antigo",
  never: "nunca subiu",
  heartbeat_missing: "heartbeat ausente",
  redis_unavailable: "Redis indisponível",
};

export function executorStatusLabel(status: string): string {
  return isExecutorStatus(status) ? EXECUTOR_STATUS_LABEL[status] : "estado não previsto";
}

// Same four-state vocabulary as `components/portfolio/portfolio-format.ts`'s
// `killSwitchLabel` (`hunter_core.domain.enums.KillSwitchState`) -- kept as
// its own copy here so the meme domain never imports across `components/portfolio`.
const KILL_SWITCH_STATE_LABEL: Record<string, string> = {
  ACTIVE: "ATIVO",
  WARNING: "AVISO",
  TRADING_DISABLED: "BLOQUEADO",
  EMERGENCY: "EMERGÊNCIA",
};

/** `""` is not a state -- it means the source itself is not configured (no `MEME_KILL_FILE`, no Redis key ever written), distinct from every real state. */
export function killSwitchStateLabel(state: string): string {
  if (state === "") return "não configurada";
  return KILL_SWITCH_STATE_LABEL[state] ?? state;
}

export function killSwitchBadgeVariant(state: string): "default" | "warning" | "negative" {
  if (state === "WARNING") return "warning";
  if (state === "TRADING_DISABLED" || state === "EMERGENCY") return "negative";
  return "default";
}

const LIVE_ORDER_STATUS_LABEL: Record<LiveOrderStatus, string> = {
  admitted: "admitida — ainda não simulada",
  refused: "recusada",
  simulated: "simulada — ainda não enviada",
  submitted_unconfirmed: "enviada — reconciliando",
  confirmed: "confirmada",
  failed: "falhou",
};

export function liveOrderStatusLabel(status: string): string {
  return isLiveOrderStatus(status) ? LIVE_ORDER_STATUS_LABEL[status] : "estado não previsto";
}

export function liveOrderStatusVariant(status: string): "default" | "warning" | "negative" | "positive" {
  if (status === "confirmed") return "positive";
  if (status === "submitted_unconfirmed") return "warning";
  if (status === "refused" || status === "failed") return "negative";
  return "default";
}

const LIVE_POSITION_STATUS_LABEL: Record<LivePositionStatus, string> = {
  open: "aberta",
  closed: "fechada",
};

export function livePositionStatusLabel(status: string): string {
  return isLivePositionStatus(status) ? LIVE_POSITION_STATUS_LABEL[status] : "estado não previsto";
}

// `LivePositionOut.mark_source` -- `LIVE_MARK_SOURCES_0028` (`infra/migrations/ddl/meme_live.py`),
// a different vocabulary from the paper desk's `curve`/`pool_tape` (`components/meme-desk/labels.ts`'s `markSourceLabel`).
const LIVE_MARK_SOURCE_LABEL: Record<string, string> = {
  solana_rpc: "marcada por leitura direta na cadeia",
  curve_snapshot: "marcada pela fotografia da curva",
  tape: "marcada pela fita",
};

export function liveMarkSourceLabel(source: string | null | undefined): string | null {
  if (!source) return null;
  return LIVE_MARK_SOURCE_LABEL[source] ?? `marcada por ${source}`;
}

/** `(reason: <slug>)` embedded in the API's `detail`, same convention as `components/meme-desk/labels.ts`'s `reasonOf`. */
function reasonOf(detail: string | null | undefined): string | undefined {
  return detail?.match(/reason:\s*([a-z0-9_]+)/i)?.[1];
}

/**
 * The named refusals the brief asks for on the REAL approve/manual/sell-now
 * flows (`.claude/state/brief-T4.17-aprovar-real-na-mesa.md` §2): the API's
 * own `mode: "live"` gate (`meme_live_disabled`), the rule set's ceilings
 * (`exceeds_max_sol_per_bet`, `rule_set_inactive`), a proposal whose deadline
 * passed (`expired`), the desk's ordinary state conflicts, and a literal,
 * named fallback for anything else -- never a silent generic message.
 */
const REAL_REASON_MESSAGE: Record<string, string> = {
  meme_live_disabled: "dinheiro real desligado na API (ENABLE_MEME_LIVE_TRADING)",
  exceeds_max_sol_per_bet: "tamanho acima do teto por aposta do conjunto de regras",
  rule_set_inactive: "o conjunto de regras usado nesta proposta não está mais ativo",
  expired: "o prazo desta proposta venceu — ela não pode mais ser aprovada",
  not_proposed: "esta proposta já foi decidida (ou expirou) — a lista será atualizada",
  decided_concurrently: "outra decisão chegou antes desta — a lista será atualizada",
  already_filled: "esta proposta já virou aposta",
  not_cancellable: "esta proposta já está encerrada",
  mint_unknown: "este mint não está no radar",
  curve_completed: "esta curva já encerrou (concluída ou migrada)",
  operator_rule_set_missing: "o conjunto de regras do operador ainda não existe",
  sell_now_already_pending: "já existe um Vender agora (REAL) pendente para esta posição",
  bet_not_open: "esta posição não está aberta",
};

/**
 * `ActionResult.problem` from any REAL action (approve, manual, sell-now) ->
 * one Portuguese sentence, always naming an unrecognized code instead of a
 * generic message ("recusa não prevista: <código>", the brief's exact words).
 */
export function realActionProblemMessage(problem: Problem): string {
  const reason = reasonOf(problem.detail);
  if (reason !== undefined && REAL_REASON_MESSAGE[reason] !== undefined) return REAL_REASON_MESSAGE[reason];

  const slug = problem.type.split("/").pop()?.toLowerCase().replace(/_/g, "-") ?? "";
  const KNOWN: Record<string, string> = {
    "insufficient-role": "Seu papel na organização não permite operar a mesa (requer Trader ou superior).",
    "idempotency-key-conflict": "Esta chave de envio já foi usada para outra ação. Feche e abra de novo para tentar.",
    unauthenticated: "Sessão não encontrada. Entre novamente.",
    "validation-error": problem.detail ?? "Dados inválidos.",
    "meme-live-position-not-found": "Posição real não encontrada — a lista será atualizada.",
    "meme-proposal-not-found": "Proposta não encontrada — a lista será atualizada.",
    "unexpected-response": "A resposta da API não veio no formato esperado. Tente novamente em instantes.",
  };
  const known = KNOWN[slug];
  if (known !== undefined) return known;

  if (problem.status === 403) return "Seu papel na organização não permite operar a mesa (requer Trader ou superior).";
  if (problem.status === 409) return "Conflito ao registrar a ação — a lista será atualizada.";
  if (problem.status >= 500) return "A mesa está indisponível no momento. Tente novamente em instantes.";
  return `recusa não prevista: ${reason ?? slug ?? problem.status}`;
}
