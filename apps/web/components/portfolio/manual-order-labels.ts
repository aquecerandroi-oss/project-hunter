/**
 * Plain-Portuguese vocabulary for the manual paper order flow (T3.72,
 * DESIGN-5 "sem backstage na copy": nenhum enum cru na tela). Check and
 * ceiling names mirror `docs/RISK_ENGINE.md` §3/§4 (`packages/risk-core/
 * hunter_risk/{decision,sizing}.py`'s own field names) -- the same wording
 * the Risk Center/Lab already use for this engine, so a trader reading both
 * screens sees one vocabulary, not two.
 */
import type { Problem } from "@hunter/shared-types";

import type { CheckState } from "@/lib/api/manual-orders-types";

/** `RiskCheck.name` -- docs/RISK_ENGINE.md §3.1/§3.2, evaluation order. */
export const RISK_CHECK_LABEL: Record<string, string> = {
  kill_switch: "Kill switch",
  portfolio_status: "Status da carteira",
  modality: "Modalidade (direção/alavancagem/produto)",
  data_quality: "Qualidade dos dados",
  market_gap: "Lacuna de coleta do mercado",
  market_in_universe: "Mercado no universo",
  signal_validity: "Validade do sinal e do stop",
  stop_distance: "Distância do stop",
  liquidity_24h: "Liquidez de 24h",
  spread: "Spread",
  book_depth: "Profundidade do livro",
  beta_validity: "Validade do beta",
  concurrent_positions: "Posições concorrentes",
  duplicate_position: "Posição duplicada no mercado",
  aggregate_risk_budget: "Orçamento de risco agregado",
  daily_loss: "Perda diária",
  drawdown: "Drawdown",
  sizing: "Dimensionamento (mínimo do mercado)",
  participation: "Participação no volume",
  slippage_estimate: "Estimativa de slippage",
  cash: "Caixa disponível",
  exposure_after: "Exposição após a entrada",
  exit_allowed: "Saída permitida",
  reduce_only: "Somente redução",
};

export function riskCheckLabel(name: string): string {
  return RISK_CHECK_LABEL[name] ?? name;
}

/** `Sizing.binding_constraint` / `LimitCap.name` -- docs/RISK_ENGINE.md §4's nine ceilings. */
export const LIMIT_CAP_LABEL: Record<string, string> = {
  requested: "Teto pedido no formulário",
  risk_per_trade: "Risco por operação",
  aggregate_risk: "Orçamento de risco agregado",
  market_participation: "Participação de mercado",
  book_depth: "Profundidade do livro",
  asset_exposure: "Exposição por ativo",
  total_exposure: "Exposição total",
  beta_exposure: "Exposição em beta (BTC)",
  cash: "Caixa disponível",
};

export function limitCapLabel(name: string): string {
  return LIMIT_CAP_LABEL[name] ?? name;
}

const CHECK_STATE_LABEL: Record<CheckState, string> = {
  passed: "Aprovado",
  failed: "Reprovado",
  unavailable: "Indisponível",
};

export function checkStateLabel(state: CheckState): string {
  return CHECK_STATE_LABEL[state];
}

/**
 * `OrderRefusedError`'s reason (`services/orders_derive.py`/`services/
 * orders.py`, embedded in `detail` as `"... (reason: <slug>)"`) -> one
 * Portuguese sentence. Every reason the manual-order write path can name
 * today, per `.claude/state/notes-T3.68.md` §1.
 */
const ORDER_REFUSED_REASON_LABEL: Record<string, string> = {
  market_unknown: "Mercado não encontrado.",
  market_not_executable_spot: "Este mercado não é SPOT executável -- escolha outro na busca.",
  short_not_supported_spot: "Venda a descoberto (short) não é suportada em SPOT neste perfil de risco (paper_v1, alavancagem máxima 1x).",
  spot_price_unavailable: "Sem preço de mercado disponível agora para esta ordem. Tente novamente em instantes.",
  spot_spread_unavailable: "Sem spread de mercado disponível agora para esta ordem. Tente novamente em instantes.",
};

function orderRefusedMessage(detail: string | null | undefined): string {
  const reason = detail?.match(/reason:\s*([a-z0-9_]+)/i)?.[1];
  if (reason !== undefined) {
    const known = ORDER_REFUSED_REASON_LABEL[reason];
    if (known !== undefined) return known;
  }
  return "A ordem não passou na validação da API. Revise os campos e tente de novo.";
}

/**
 * `ActionResult.problem` -> one Portuguese sentence, never a raw
 * `type`/status code shown to the trader (CLAUDE.md/DESIGN-5). `type` slugs
 * below are the ones `routers/orders.py`/`services/admission.py` actually
 * answer with (T3.68, confirmed against `apps/api/hunter_api/errors.py` and
 * `services/admission.py`'s `OrderRefusedError`/`OrderReplayConflictError`/
 * `WalletNotOpenError`, plus `auth/rbac.py`'s `InsufficientRoleError`):
 * `order-refused` (422, reason in `detail`), `idempotency-key-conflict` (409,
 * a *different* order replaying the same key), `wallet-not-open` (409),
 * `insufficient-role` (403). An unrecognized `type` still gets an honest,
 * non-technical sentence built from the status code, never the raw slug or
 * the API's own (often English) `detail`.
 */
export function manualOrderProblemMessage(problem: Problem): string {
  const slug = problem.type.split("/").pop()?.toLowerCase().replace(/_/g, "-") ?? "";

  if (slug === "order-refused") return orderRefusedMessage(problem.detail);

  const KNOWN: Record<string, string> = {
    "idempotency-key-conflict": "Esta chave de envio já foi usada para uma ordem diferente. Abra um novo formulário para tentar de novo.",
    "wallet-not-open": "A carteira não está aberta para receber ordens agora.",
    "insufficient-role": "Seu papel na organização não permite enviar ordens (requer Trader ou superior).",
    "portfolio-not-found": "Carteira não encontrada.",
    "order-request-not-found": "Solicitação de ordem não encontrada.",
    "unexpected-response": "A resposta da API não veio no formato esperado. Tente novamente em instantes.",
    unauthenticated: "Sessão não encontrada. Entre novamente.",
    "validation-error": problem.detail ?? "Dados inválidos.",
  };
  const known = KNOWN[slug];
  if (known !== undefined) return known;

  if (problem.status === 403) return "Seu papel na organização não permite enviar ordens (requer Trader ou superior).";
  if (problem.status === 409) return "Conflito ao registrar a ordem -- verifique se ela já não foi enviada.";
  if (problem.status === 422) return "A ordem não passou na validação da API. Revise os campos e tente de novo.";
  if (problem.status >= 500) return "O serviço de ordens está indisponível no momento. Tente novamente em instantes.";
  return "Não foi possível registrar a ordem agora. Tente novamente.";
}
