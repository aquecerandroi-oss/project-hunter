-- EXP-M26 J — o export da leitura única da H-022 (lê desfechos: só no instante da leitura,
-- corte + 2 h, nunca antes). Somente leitura: rodar numa sessão com
--   PGOPTIONS="-c default_transaction_read_only=on"
-- (o mesmo `q.sh` de .claude/state/m26/), com psql -At (uma linha JSON por registro):
--   cat export_h022.sql | ssh hunter-vps 'docker exec -i -e PGOPTIONS="-c default_transaction_read_only=on" \
--     $(docker ps -qf name=postgres | head -1) psql -U hunter -d hunter -X -At -v ON_ERROR_STOP=1' > h022.jsonl
-- É o retrato da leitura: tirar em [L, L + 1 h], L = corte + 2 h (o J recusa fora disso).
-- Quatro tipos de linha: 'meta' (now() da transação = o instante do retrato), 'braco' (os três
-- conjuntos), 'oportunidade' (R1 + proposta + aposta + token + covariável), 'proposta' (a 1.ª
-- proposta por braço e mint: acha órfãs e piloto).
SELECT json_build_object('tipo', 'meta', 'exportado_em', now())::text
UNION ALL
SELECT json_build_object(
  'tipo', 'braco', 'rule_set_id', rs.id, 'created_at', rs.created_at,
  'retired_at', rs.retired_at, 'size_sol', rs.params ->> 'size_sol')::text
FROM meme_rule_sets rs
WHERE rs.id IN ('01994d00-6c1a-7000-8000-00000000001f', '01994d00-6c1a-7000-8000-000000000020',
                '01994d00-6c1a-7000-8000-000000000021')
UNION ALL
SELECT json_build_object(
  'tipo', 'oportunidade', 'rule_set_id', o.rule_set_id, 'mint', o.mint,
  'evaluated_at', o.evaluated_at, 'features_end_time', o.features_end_time,
  'features_computed_at', o.features_computed_at, 'fidelity', o.fidelity,
  'coverage_status', o.coverage_status, 'line_reason', o.line_reason,
  'higher_lows', o.higher_lows, 'breakout_15m', o.breakout_15m,
  'distance_to_support_pct', o.distance_to_support_pct, 'mcap_slope_15m', o.mcap_slope_15m,
  'curve_progress_pct', o.curve_progress_pct, 'proposal_refusals', o.proposal_refusals,
  'no_proposal_reason', o.no_proposal_reason, 'proposal_id', o.proposal_id,
  'proposal_status', p.status, 'proposal_refusal', p.refusal,
  'prior_other_bet', EXISTS (
    SELECT 1 FROM meme_paper_bets ob
    WHERE ob.mint = o.mint AND ob.entry_at < o.features_end_time
      AND ob.rule_set_id NOT IN ('01994d00-6c1a-7000-8000-00000000001f',
                                 '01994d00-6c1a-7000-8000-000000000020',
                                 '01994d00-6c1a-7000-8000-000000000021')),
  'bet_id', b.id, 'entry_at', b.entry_at,
  'fill_observed_at', b.entry -> 'snapshot' ->> 'observed_at',
  'fill_source', b.entry -> 'snapshot' ->> 'source',
  'sol_spent', b.entry ->> 'sol_spent', 'bet_status', b.status, 'exit_at', b.exit_at,
  'exit_reason', b.exit ->> 'reason', 'pnl_sol', b.pnl_sol,
  'outcome_quality', b.outcome_quality,
  'sale_observed_at', b.exit -> 'snapshot' ->> 'observed_at',
  'sale_complete', (b.exit -> 'snapshot' ->> 'complete')::boolean,
  'token_completed_at', t.completed_at, 'token_migrated_at', t.migrated_at,
  'high_water_x', b.high_water_x, 'fee_buy_sol', b.entry ->> 'fee_sol',
  'fee_sell_sol', b.exit ->> 'fee_sol', 'curve_proceeds_sol', b.exit ->> 'curve_proceeds_sol')::text
FROM meme_mature_opportunities o
LEFT JOIN meme_proposals p ON p.id = o.proposal_id
LEFT JOIN meme_paper_bets b ON b.proposal_id = o.proposal_id
LEFT JOIN meme_tokens t ON t.mint = o.mint
WHERE o.rule_set_id IN ('01994d00-6c1a-7000-8000-00000000001f',
                        '01994d00-6c1a-7000-8000-000000000020',
                        '01994d00-6c1a-7000-8000-000000000021')
UNION ALL
SELECT json_build_object(
  'tipo', 'proposta', 'rule_set_id', p.rule_set_id, 'mint', p.mint,
  'proposed_at', min(p.proposed_at))::text
FROM meme_proposals p
WHERE p.rule_set_id IN ('01994d00-6c1a-7000-8000-00000000001f',
                        '01994d00-6c1a-7000-8000-000000000020',
                        '01994d00-6c1a-7000-8000-000000000021')
GROUP BY p.rule_set_id, p.mint;
