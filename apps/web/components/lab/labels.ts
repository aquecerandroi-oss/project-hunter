/**
 * Centralized pt-BR labels for every enum-ish value the Lab renders
 * (docs/DESIGN.md §2 "sem backstage na copy": no raw enum/status code reaches
 * the screen). One dictionary per domain, each covered by a test
 * (`tests/lab-labels.test.ts`) that fails when a new member has no label --
 * brief T3.24b's own aceite ("todo membro de status/purpose/result/tracking
 * tem rótulo em pt sem `_`").
 *
 * `status`/`purpose` were previously scattered (`lab-scoreboard.ts`'s
 * `SCOREBOARD_STATUS_LABEL`, `lab-strategy-cell.tsx`'s `purposeLabel`,
 * `lab-signal-chips.tsx`'s `TRACKING_LABEL`/`RESULT_LABEL`) -- moved here
 * verbatim except `deprecated`, which brief T3.24b renames "descontinuada" ->
 * "substituída" (the word a reader already sees on `superseded_by`'s own
 * link, "substituída por ...").
 */
import type { OutcomeResult, ShadowTrackingState, StrategyVersionStatus } from "@/lib/api/lab-types";

export const STATUS_LABEL: Record<StrategyVersionStatus, string> = {
  active: "ativa",
  deprecated: "substituída",
  draft: "rascunho",
};

export function statusLabel(status: string): string {
  return STATUS_LABEL[status as StrategyVersionStatus] ?? status;
}

// `strategy_versions.purpose` (T3.15e): "research_only" never spends the
// wallet, "paper" is the coorte that does. The map stays total so an
// unexpected value still renders its own raw code instead of disappearing.
export const PURPOSE_LABEL: Record<string, string> = {
  research_only: "pesquisa",
  paper: "paper",
  live: "live",
};

export function purposeLabel(purpose: string): string {
  return PURPOSE_LABEL[purpose] ?? purpose;
}

// `signal_outcomes.tracking_state` -- the axis that answers "is this
// tracking still going?" (distinct from `result`, the financial outcome).
export const TRACKING_LABEL: Record<ShadowTrackingState, string> = {
  pending_entry: "pendente de entrada",
  active: "ativo",
  terminal: "encerrado",
  no_entry: "sem entrada",
  censored: "censurado",
};

export function trackingLabel(state: string): string {
  return TRACKING_LABEL[state as ShadowTrackingState] ?? state;
}

// `signal_outcomes.result` -- how the hypothetical trade ended.
export const RESULT_LABEL: Record<OutcomeResult, string> = {
  target: "alvo",
  stop: "stop",
  expired: "expirado",
  invalidated: "invalidado",
  open: "aberto",
};

export function resultLabel(result: string): string {
  return RESULT_LABEL[result as OutcomeResult] ?? result;
}

// --- Addendum T3.24b (A2): replication status/evidence vocabulary ---

/**
 * `replication.status` (REPLICATION.md §6). `"none"` never reaches this
 * function -- the block itself is `null` and the whole "Replicação" section
 * is not rendered (brief A2: "none -> não mostrar o bloco").
 */
export const REPLICATION_STATUS_LABEL: Record<string, string> = {
  promissora: "promissora",
  replicando: "replicando",
  real: "real",
  refutada: "refutada",
};

export function replicationStatusLabel(status: string): string {
  return REPLICATION_STATUS_LABEL[status] ?? status;
}

/** `SiblingArmOut.evidence` (D15): which population an arm's own outcomes came from. */
export const EVIDENCE_LABEL: Record<string, string> = {
  prospective: "prospectivo",
  replay: "replay",
  mixed: "misto",
};

export function evidenceLabel(evidence: string | null): string {
  if (evidence === null) return "sem resultado ainda";
  return EVIDENCE_LABEL[evidence] ?? evidence;
}

/**
 * `out_of_sample.reason` / `siblings.reason` / `market_halves.reason` /
 * `bootstrap.refused_reason` (`packages/indicators/hunter_indicators/replication/{protocol,split,bootstrap}.py`,
 * REPLICATION.md §3) -- rendered as a short pt phrase, with the raw backend
 * code kept in `title` (brief A2). Every code below is copied verbatim from
 * that module (not guessed); most carry a `prefix: detail` shape (e.g.
 * `"imaturo: 3 de 7 positivas"`), so the lookup splits on `:` the same way
 * `lab-format.ts`'s `reasonLabel` does -- an unlisted detail still shows its
 * known prefix, and a wholly unknown code still renders instead of
 * disappearing.
 */
const REPLICATION_REASON_LABELS: Record<string, string> = {
  sem_irmas: "sem irmãs ainda",
  sem_promising_at: "ainda não validada",
  imatura: "metade ainda imatura",
  imaturo: "ainda imaturo",
  maioria_impossivel: "maioria de irmãs positivas já impossível",
  expectancy_nao_positiva: "expectância fora da amostra não é positiva",
  intervalo_negativo: "intervalo de confiança negativo",
  intervalo_cruza_zero: "intervalo de confiança cruza zero",
  intervalo_por_dia_cruza_zero: "intervalo por dia cruza zero",
  amostra_insuficiente: "amostra insuficiente",
  grupos_insuficientes: "dias distintos insuficientes",
};

export function replicationReasonLabel(reason: string): string {
  if (REPLICATION_REASON_LABELS[reason]) return REPLICATION_REASON_LABELS[reason];
  const [prefix, ...rest] = reason.split(":");
  const detail = rest.join(":").trim();
  if (prefix && REPLICATION_REASON_LABELS[prefix]) {
    return detail ? `${REPLICATION_REASON_LABELS[prefix]} (${detail})` : REPLICATION_REASON_LABELS[prefix];
  }
  return `motivo: ${reason}`;
}
