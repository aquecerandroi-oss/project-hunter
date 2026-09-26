/**
 * The real executor's own vocabulary of named refusals -- `docs/RISK_ENGINE_MEME.md`
 * §1 (scope) and §4 (the 25 admission checks), plus the operational refusals
 * named in §8/§9/§12 and `.claude/state/notes-T4.14.md`. These are the codes
 * that can land in `LiveOrderOut.reason`/`first_refusal`,
 * `LiveExecutorOut.last_refusal` and `LiveExecutorOut.blocked_exits` values --
 * a different vocabulary from the paper desk's `meme_desk.py` refusals in
 * `components/meme-desk/labels.ts`. DESIGN-5: no enum value ever reaches the
 * screen raw; an unrecognized code is still shown, always prefixed, never
 * bare (`refusalLabel(null)`/`recusa: <code>` convention).
 */
const CHECK_REFUSAL_LABEL: Record<string, string> = {
  // check 1 -- kill_switch
  kill_switch_blocked: "corta-circuito bloqueando entradas",
  daily_loss_cap_latched: "trava diária de perda acionada (só o dono destrava)",
  // check 2 -- wallet_status
  wallet_inactive: "carteira inativa",
  agent_disabled: "agente desabilitado",
  marks_incomplete: "marcações de alguma posição aberta desatualizadas",
  // check 3 -- live_gate
  meme_live_disabled: "dinheiro real desligado na API (ENABLE_MEME_LIVE_TRADING)",
  // check 4/§1 -- program_allowed
  program_not_allowed: "programa fora da lista permitida",
  // check 5/§1 -- quote_supported
  unsupported_quote: "cotação não suportada (só SOL)",
  // check 6 -- identity_match
  identity_mismatch: "identidade do mint não bate entre proposta, estado e contexto",
  // check 7 -- state_freshness
  curve_state_stale: "estado da curva desatualizado",
  curve_state_undated: "estado da curva sem carimbo de tempo",
  curve_state_clock_skew: "relógio do estado da curva à frente (NTP)",
  commitment_too_weak: "confirmação da leitura fraca demais (abaixo de confirmed)",
  // check 8 -- token_age
  token_too_young: "token jovem demais",
  token_too_old: "token velho demais",
  token_age_unknown: "idade do token desconhecida",
  // check 9/§1 -- curve_progress
  progress_below_window: "progresso da curva abaixo da janela",
  progress_above_window: "progresso da curva acima da janela",
  curve_complete: "curva concluída (fórmula não vale mais)",
  progress_denominator_missing: "denominador do progresso ausente",
  // check 10 -- creator_behaviour
  creator_net_seller: "criador é vendedor líquido",
  creator_flow_unknown: "fluxo do criador desconhecido",
  // check 11 -- bundled_share
  bundled_share_above_cap: "fração comprada em bundle acima do teto",
  bundled_share_unmeasurable: "fração comprada em bundle não medida (radar ainda não mede)",
  // check 12 -- top10_share
  top10_share_above_cap: "concentração dos 10 maiores acima do teto",
  top10_share_unknown: "concentração dos 10 maiores desconhecida",
  holder_denominator_invalid: "denominador de holders inválido",
  // check 13 -- mayhem_policy
  mayhem_not_allowed: "moeda Mayhem sem política aprovada",
  mayhem_state_unknown: "estado do agente Mayhem desconhecido",
  // check 14 -- rug_history
  token_rugged_no_reentry: "token já marcado como rug — sem reentrada",
  rug_cooldown_active: "carteira em pausa após detecção de rug",
  // check 15/16 -- duplicate/concurrent
  duplicate_position: "já existe posição ou pendência neste mint",
  max_open_positions: "teto de posições simultâneas atingido",
  // check 17 -- wallet_cap
  wallet_over_max_sol: "saldo da carteira acima do teto",
  wallet_unrecognized_holdings: "carteira com token não reconhecido",
  // check 18 -- daily_loss
  daily_loss_cap_reached: "teto de perda diária atingido",
  // check 19 -- slippage_cap
  slippage_above_cap: "slippage pedido acima do teto",
  // check 20 -- fee_caps
  priority_fee_above_cap: "priority fee acima do teto",
  jito_tip_above_cap: "tip do Jito acima do teto",
  // check 21 -- participation
  participation_above_cap: "tamanho acima da fração do volume orgânico permitida",
  volume_window_incomplete: "janela de volume do minuto incompleta",
  volume_unavailable: "volume orgânico indisponível (sem feed pago)",
  // check 22 -- price_impact
  price_impact_above_cap: "impacto da própria compra na curva acima do teto",
  // check 23 -- sizing
  below_min_sol: "tamanho final abaixo do mínimo economicamente sensato",
  // check 24 -- sol_available
  insufficient_sol: "SOL disponível insuficiente para tamanho + taxas + rent",
  // check 25 -- exposure_after
  exposure_after_above_cap: "exposição depois desta entrada acima do teto",
  // §1 -- other scope prohibitions
  leverage_not_supported: "alavancagem/short não suportado nesta classe",
  pumpswap_buy_not_allowed: "compra no PumpSwap não permitida (só saída)",
  token_creation_not_allowed: "criação de moeda não permitida",
  foreign_launchpad: "moeda de outro launchpad (não é pump.fun)",
  multi_wallet_bundle_not_allowed: "bundle com mais de uma carteira nossa",
  not_in_scope: "instrução fora do escopo deste contrato",
  // §8/§9/§12 -- operational
  rpc_unreachable: "RPC inalcançável — entrada adiada",
  reservation_expired: "reserva da aprovação expirou (mais de 5 s)",
  unverified_transaction: "transação não passou no verificador — recusada antes de assinar",
  reconciliation_mismatch: "divergência entre a cadeia e o livro — entradas bloqueadas até reconciliar",
  pumpswap_sell_not_implemented: "presa após migração — venda no PumpSwap ainda não existe; saia pelo site",
  kill_switch_blocked_before_signing: "corta-circuito bloqueou entre a admissão e a assinatura",
  program_upgraded: "o programa da pump.fun mudou — recusa até revalidar a paridade",
  // §12/§9c -- small-test authorization
  small_test_unauthorized: "teste pequeno sem autorização por escrito",
  small_test_invalid: "autorização do teste pequeno inválida",
  small_test_without_decision_note: "autorização do teste pequeno sem decisão registrada no Obsidian",
  small_test_expired: "autorização do teste pequeno expirada",
  small_test_scope_exhausted: "escopo do teste pequeno esgotado (nº de compras ou SOL do escopo)",
  // T4.96: above zero, but below the minimum ticket of the profile that tried to buy.
  small_test_below_min: "restante do escopo do teste pequeno abaixo do mínimo por compra deste perfil",
};

/** `curve_not_found`/`curve_complete` (mark reason) and the `rpc_unreachable:<Type>`/`fill_decode_failed:<Type>`/`simulation_failed:<motivo>` prefixes the executor writes with a dynamic suffix. */
const MARK_REASON_LABEL: Record<string, string> = {
  curve_complete: "curva concluída — sem preço marginal para vender tudo agora",
  curve_not_found: "curva não encontrada na última leitura",
};

/** One Portuguese sentence for a named refusal from the real executor -- never a bare, untranslated slug (DESIGN-5). An unrecognized code is still shown, always prefixed with "recusa:". */
export function executorRefusalLabel(code: string | null | undefined): string | null {
  if (!code) return null;
  const known = CHECK_REFUSAL_LABEL[code];
  if (known !== undefined) return known;
  if (code.startsWith("rpc_unreachable:")) return `RPC inalcançável (${code.slice("rpc_unreachable:".length)})`;
  if (code.startsWith("fill_decode_failed:")) return `fill não decodificado ainda (${code.slice("fill_decode_failed:".length)}) — reconcilia sozinho`;
  if (code.startsWith("simulation_failed:")) return `falhou na simulação (${code.slice("simulation_failed:".length)}) — nada assinado`;
  return `recusa: ${code}`;
}

/** `LivePositionOut.mark_reason` -- why there is no live mark right now. */
export function markReasonLabel(reason: string | null | undefined): string | null {
  if (!reason) return null;
  const known = MARK_REASON_LABEL[reason];
  if (known !== undefined) return known;
  if (reason.startsWith("rpc_unreachable:")) return `RPC inalcançável (${reason.slice("rpc_unreachable:".length)})`;
  return `recusa: ${reason}`;
}

/**
 * The stage-1 "modo sozinho" (T4.28/T4.28e/T4.28f, `hunter_meme_executor.auto_approve`)
 * skip vocabulary -- passes where the robot did **not** even open a proposal,
 * named in `LiveExecutorOut.auto_skipped`. A different vocabulary from
 * `CHECK_REFUSAL_LABEL` above: these are the robot's own pre-filters (a
 * proposal that would certainly be refused, or a budget that is not there),
 * never one of the 25 admission checks. `scope_exhausted:<max_trades|max_total_sol>`
 * is the one dynamic member (`auto_approve.py::auto_approve_once`).
 */
const AUTO_SKIP_LABEL: Record<string, string> = {
  expired: "proposta expirou antes de decidir",
  too_old: "proposta velha demais para o robô decidir (só o clique, agora)",
  mint_busy: "mint já tem posição aberta ou compra em voo",
  mint_busy_superseded: "mint tinha posição aberta ou compra em voo — proposta descartada (dado velho); o portão propõe de novo",
  recently_refused: "mint em carência — recusa recente que o relógio não desfaz",
  suggested_incomplete: "sugestão do conjunto de regras incompleta (sem tamanho)",
  exceeds_max_sol_per_bet: "tamanho acima do teto por aposta do conjunto de regras",
  hourly_cap: "teto de aprovações da hora atingido",
  tick_cap: "já abriu uma proposta neste tique",
  mint_repeated: "mesmo mint já escolhido neste tique",
  decided_concurrently: "outra decisão chegou antes (clique ou outro tique)",
  kill_switch: "corta-circuito bloqueando entradas",
  program_upgraded: "o programa da pump.fun mudou — pausado até revalidar",
  small_test_below_min: "restante do escopo abaixo do mínimo por compra — o robô não abre",
};

const SCOPE_EXHAUSTED_LABEL: Record<string, string> = {
  max_trades: "esgotado — nº de compras",
  max_total_sol: "esgotado — SOL do escopo",
};

/** `ScopeUse.exhausted` (`scope.py`) -- which counter closed the tap. Shared by the skip chip below and the scope line in `live-format.ts`'s `autoScopeLine` so the two never disagree on the wording. */
export function scopeExhaustedLabel(reason: string): string {
  return SCOPE_EXHAUSTED_LABEL[reason] ?? `esgotado (${reason})`;
}

/** One Portuguese sentence for a stage-1 skip reason -- never a bare, untranslated slug (DESIGN-5). An unrecognized code is still shown, always prefixed with "pulo:". */
export function autoSkipLabel(code: string): string {
  const known = AUTO_SKIP_LABEL[code];
  if (known !== undefined) return known;
  if (code.startsWith("scope_exhausted:")) return `escopo ${scopeExhaustedLabel(code.slice("scope_exhausted:".length))}`;
  // T4.94: the per-lane breakdown of `too_old` (`auto_plan.py`), `too_old:<series>`.
  if (code.startsWith("too_old:")) return `proposta velha demais — pista ${code.slice("too_old:".length)}`;
  return `pulo: ${code}`;
}

/**
 * `LiveExecutorOut.gates_reload_error` (T4.28d/T4.28f) -- the reload's own
 * failure vocabulary (`hunter_core.execution.meme.gates`), distinct from the
 * admission's. A `deferred:<reason>` prefix means the process is giving the
 * parse failure one tick of grace before latching (T4.28f) -- the previous
 * policy still holds.
 */
const GATES_RELOAD_ERROR_LABEL: Record<string, string> = {
  gates_file_missing: "arquivo de portões não encontrado",
  gates_file_invalid: "arquivo de portões ilegível (JSON quebrado ou incompleto)",
  gates_schema_mismatch: "arquivo de portões com schema não reconhecido",
  gate_a_engineering_not_passed: "portão A (engenharia) não assinado",
  gate_b_evidence_not_passed: "portão B (evidência) não assinado",
  gate_c_owner_not_enabled: "portão C (dono) não habilitado",
  gates_unsigned: "arquivo de portões sem assinatura",
  gates_date_in_future: "data de assinatura no futuro no arquivo de portões",
  gates_expired: "autorização dos portões expirada",
  gates_without_evidence: "portão B sem evidência anexada",
  small_test_invalid: "autorização do teste pequeno inválida no arquivo",
  small_test_unauthorized: "teste pequeno sem autorização por escrito no arquivo",
  small_test_expired: "autorização do teste pequeno expirada no arquivo",
  auto_approve_needs_small_test: "modo sozinho ligado sem teste pequeno escrito — trava por contrato",
};

function gatesReasonLabel(reason: string): string {
  return GATES_RELOAD_ERROR_LABEL[reason] ?? `recusa: ${reason}`;
}

/** One Portuguese sentence for the gates reload's own error, or `null` when the last read was good. Never a bare, untranslated slug (DESIGN-5). */
export function gatesReloadErrorLabel(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const deferred = raw.startsWith("deferred:") ? raw.slice("deferred:".length) : null;
  const known = gatesReasonLabel(deferred ?? raw);
  return deferred !== null
    ? `leitura anterior mantida por um tique (falha ainda não confirmada): ${known}`
    : `trava dos portões: ${known}`;
}

/**
 * `LiveExecutorOut.kill_switch_latch_reason` -- either the wallet's daily-loss
 * latch (`daily_loss_cap_reached`, `CHECK_REFUSAL_LABEL` above) or a
 * `gates_invalid:<reason>` this process latched itself when the gates file
 * stopped being valid in flight (T4.28d, `GATES_LATCH_PREFIX`). `null` means
 * not latched -- callers already gate this on `kill_switch_latched`.
 */
export function killSwitchLatchReasonLabel(raw: string | null | undefined): string | null {
  if (!raw) return null;
  if (raw.startsWith("gates_invalid:")) return `portões inválidos — ${gatesReasonLabel(raw.slice("gates_invalid:".length))}`;
  return executorRefusalLabel(raw) ?? `recusa: ${raw}`;
}
