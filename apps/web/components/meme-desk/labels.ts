/**
 * Operator-desk vocabulary (DESIGN-5 "sem backstage na copy": no enum value
 * reaches the screen raw). `Record<Enum, string>` makes the compiler enforce
 * completeness for the unions `lib/api/meme-desk-types.ts` names;
 * `tests/meme-desk-labels.test.ts` iterates the same arrays for a second,
 * explicit exhaustiveness check (the `components/meme/labels.ts` convention).
 */
import type { Problem } from "@hunter/shared-types";

import { isMemeBetLeg, isMemeExitReason, isMemeProposalStatus, type MemeBetLeg, type MemeExitReason, type MemeProposalStatus } from "@/lib/api/meme-desk-types";

const PROPOSAL_STATUS_LABEL: Record<MemeProposalStatus, string> = {
  proposed: "Aguardando aval",
  approved: "Aprovada — aguardando fotografia",
  rejected: "Recusada",
  expired: "Expirada",
  filled: "Preenchida",
  unfilled: "Não preenchida",
};

export function proposalStatusLabel(status: string): string {
  return isMemeProposalStatus(status) ? PROPOSAL_STATUS_LABEL[status] : "estado não previsto";
}

const EXIT_REASON_LABEL: Record<MemeExitReason, string> = {
  target: "alvo atingido",
  trailing: "trailing disparou",
  time_stop: "espera máxima",
  migrated: "curva migrou",
  creator_dump: "criador vendeu",
  sell_now: "vender agora (operador)",
  rug_no_snapshot: "rug — sem fotografia",
  // T4.13: the same words `hunter_api.schemas.meme_tests.EXIT_REASON_PT` writes to the CSV.
  max_loss: "perda máxima (piso)",
  line_broken: "linha rompida",
  // T4.11: the pool's tape silent for 15 min with the mark at or under half the entry.
  dead: "morta",
};

/** T4.11 (`0029`): where the open bet's mark comes from once the coin left the curve. */
export function markSourceLabel(source: string | null | undefined): string | null {
  if (!source) return null;
  if (source === "curve") return "marcada pela curva";
  if (source === "pool_tape") return "marcada pela pool (fita)";
  return `marcada por ${source}`;
}

/** "marca envelhecida há 930s" once the tape has been silent for 15 min (T4.11). */
export function markStaleLabel(staleS: number | null | undefined): string | null {
  return typeof staleS === "number" && staleS >= 900 ? `marca envelhecida há ${Math.round(staleS)}s` : null;
}

export function exitReasonLabel(reason: string | null | undefined): string {
  if (!reason) return "saída sem motivo registrado";
  return isMemeExitReason(reason) ? EXIT_REASON_LABEL[reason] : "motivo não previsto";
}

// T4.10b: the exact words brief T4.10 asks the desk to show for each leg.
const BET_LEG_LABEL: Record<MemeBetLeg, string> = {
  probe: "semi-comprado (sonda)",
  scale: "escalado (perna 2)",
  single: "aposta única",
};

export function betLegLabel(leg: string): string {
  return isMemeBetLeg(leg) ? BET_LEG_LABEL[leg] : "perna não prevista";
}

/** `meme_proposals.refusal` (contract §Tabelas) -- named by the loop when a proposal ends `unfilled`. */
const REFUSAL_LABEL: Record<string, string> = {
  no_later_snapshot: "sem fotografia posterior em 3 min",
  migrated_before_fill: "a curva migrou antes do preenchimento",
  exceeds_max_sol_per_bet: "acima do teto por aposta do conjunto",
  daily_loss_cap: "teto de perda diária do conjunto atingido",
  cancelled: "cancelada pelo operador",
};

export function refusalLabel(refusal: string | null | undefined): string | null {
  if (!refusal) return null;
  return REFUSAL_LABEL[refusal] ?? `recusa: ${refusal}`;
}

const QUOTE_REASON_LABEL: Record<string, string> = {
  no_snapshot_yet: "sem fotografia da curva ainda — o laço cota na próxima",
  unpriceable_reserves: "reservas não cotáveis na última fotografia",
};

export function quoteReasonLabel(reason: string | null | undefined): string {
  if (!reason) return "sem cotação registrada";
  return QUOTE_REASON_LABEL[reason] ?? "sem cotação registrada";
}

const RULE_SET_KIND_LABEL: Record<string, string> = {
  research_only: "pesquisa — aprova sozinho",
  operator: "operador — espera o aval",
};

export function ruleSetKindLabel(kind: string): string {
  return RULE_SET_KIND_LABEL[kind] ?? kind;
}

const ORIGIN_LABEL: Record<string, string> = { rules: "do laço", operator: "manual" };

export function originLabel(origin: string): string {
  return ORIGIN_LABEL[origin] ?? origin;
}

/** `(reason: <slug>)` embedded in the API's `detail` (`services/meme_desk.py`) -> one Portuguese sentence. */
const REASON_MESSAGE: Record<string, string> = {
  exceeds_max_sol_per_bet: "O tamanho pedido está acima do teto por aposta do conjunto de regras.",
  mint_unknown: "Este mint não está no radar — só dá para comprar o que o radar acompanha.",
  curve_completed: "Esta curva já encerrou (concluída ou migrada); não há mais compra na curva.",
  operator_rule_set_missing: "O conjunto de regras do operador ainda não existe no banco; a mesa manual fica indisponível até o laço criá-lo.",
  not_proposed: "Esta proposta já foi decidida (ou expirou) — a lista será atualizada.",
  expired: "O prazo desta proposta venceu; ela não pode mais ser aprovada.",
  decided_concurrently: "Outra decisão chegou antes desta — a lista será atualizada.",
  already_filled: "Esta proposta já virou aposta; use Vender agora na aposta aberta.",
  not_cancellable: "Esta proposta já está encerrada; não há o que cancelar.",
  bet_not_open: "Esta aposta não está aberta.",
  sell_now_already_pending: "Já existe um Vender agora pendente para esta aposta — o laço vende na próxima fotografia.",
  desk_replay_conflict: "Esta chave de envio já foi usada para outra ação. Feche e abra de novo para tentar.",
};

function reasonOf(detail: string | null | undefined): string | undefined {
  return detail?.match(/reason:\s*([a-z0-9_]+)/i)?.[1];
}

/**
 * `ActionResult.problem` -> one Portuguese sentence, never a raw type/status
 * (the `manual-order-labels.ts` convention). Slugs are the ones
 * `routers/meme_desk.py`/`services/meme_desk.py` actually answer with.
 */
export function memeDeskProblemMessage(problem: Problem): string {
  const slug = problem.type.split("/").pop()?.toLowerCase().replace(/_/g, "-") ?? "";
  const reason = reasonOf(problem.detail);
  if (reason !== undefined && REASON_MESSAGE[reason] !== undefined) return REASON_MESSAGE[reason];

  const KNOWN: Record<string, string> = {
    "idempotency-key-conflict": REASON_MESSAGE.desk_replay_conflict ?? "Chave de envio já usada.",
    "insufficient-role": "Seu papel na organização não permite operar a mesa (requer Trader ou superior).",
    "meme-proposal-not-found": "Proposta não encontrada — a lista será atualizada.",
    "meme-bet-not-found": "Aposta não encontrada — a lista será atualizada.",
    "unexpected-response": "A resposta da API não veio no formato esperado. Tente novamente em instantes.",
    unauthenticated: "Sessão não encontrada. Entre novamente.",
    "validation-error": problem.detail ?? "Dados inválidos.",
  };
  const known = KNOWN[slug];
  if (known !== undefined) return known;

  if (problem.status === 403) return "Seu papel na organização não permite operar a mesa (requer Trader ou superior).";
  if (problem.status === 409) return "Conflito ao registrar a ação — a lista será atualizada.";
  if (problem.status === 422) return "A ação não passou na validação da API. Revise os campos e tente de novo.";
  if (problem.status >= 500) return "A mesa está indisponível no momento. Tente novamente em instantes.";
  return "Não foi possível registrar a ação agora. Tente novamente.";
}
