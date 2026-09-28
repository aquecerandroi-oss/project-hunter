-- EXP-M26 J — o export da leitura única da H-022 (lê desfechos: só no instante da leitura,
-- corte + 2 h, nunca antes). Somente leitura: rodar numa sessão com
--   PGOPTIONS="-c default_transaction_read_only=on"
-- (o mesmo `q.sh` de .claude/state/m26/), com psql -At (uma linha JSON por registro):
--   cat export_h022.sql | ssh hunter-vps 'docker exec -i -e PGOPTIONS="-c default_transaction_read_only=on" \
--     $(docker ps -qf name=postgres | head -1) psql -U hunter -d hunter -X -At -v ON_ERROR_STOP=1' > h022.jsonl
-- É o retrato da leitura: tirar em [L, L + 1 h], L = corte + 2 h (o J recusa fora disso).
-- Cinco tipos de linha: 'meta' (now() da transação = o instante do retrato), 'braco' (os três
-- conjuntos), 'oportunidade' (R1 + proposta + aposta + covariável), 'proposta' (a 1.ª
-- proposta por braço e mint: acha órfãs e piloto) e 'estado_token' (por mint com
-- oportunidade: o token corrente e TODO o seu histórico de completed_at/migrated_at,
-- meme_token_state_history, 0067). O J lê completed_at/migrated_at COMO CONHECIDOS EM L —
-- a última mudança com recorded_at <= L —, nunca a linha corrente: L só é conhecido depois
-- de ler o export (o corte vem das inscrições), por isso o SQL entrega o histórico inteiro
-- e a resolução em L é do código (estado_token.em), com a via dita por aposta
-- (token_estado_via: history | current_row_pre_history | historico_diverge | token_ausente;
-- só history é estado conhecido em L).
-- DOIS comandos, nesta ordem (psql em autocommit: cada um na sua transação). O 1.º é a
-- linha 'meta' e a PROVA DE VISIBILIDADE, lida ANTES do snapshot dos dados: o xact_start
-- mais antigo das transações com xid ainda em voo nesta base (qualquer backend), quantas
-- delas não mostram xact_start (track_activities desligado), quantas transações preparadas
-- (2PC: o PREPARE carimba e a visibilidade vem depois), o maior recuo do carimbo na ordem do
-- id no histórico inteiro, e se o papel enxerga de fato a atividade de todos (superusuário
-- ou pg_read_all_stats com USAGE — MEMBER sem herança não basta). Uma transação que carimbou
-- até L e ainda não estava visível tem xact_start <= L e segue em voo aqui; o J recusa esse
-- export (ExportSemProvaDeVisibilidade) e o seguinte, depois do commit, é o aceito.
SELECT json_build_object(
  'tipo', 'meta', 'exportado_em', now(),
  'escritoras_abertas_desde', w.desde, 'escritoras_sem_inicio', w.sem_inicio,
  'preparadas', (SELECT count(*) FROM pg_prepared_xacts p WHERE p.database = current_database()),
  'relogio_recuou_s', (
    SELECT COALESCE(max(extract(epoch FROM s.antes - s.recorded_at)), 0)
    FROM (SELECT h.recorded_at, max(h.recorded_at) OVER (
            ORDER BY h.id ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS antes
          FROM meme_token_state_history h) s),
  've_toda_atividade', (SELECT r.rolsuper FROM pg_roles r WHERE r.rolname = current_user)
    OR pg_has_role(current_user, 'pg_read_all_stats', 'USAGE'))::text
FROM (SELECT min(a.xact_start) AS desde, count(*) FILTER (WHERE a.xact_start IS NULL) AS sem_inicio
      FROM pg_stat_activity a
      WHERE a.backend_xid IS NOT NULL AND a.pid <> pg_backend_pid()
        AND (a.datname = current_database() OR a.datname IS NULL)) w;
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
  'high_water_x', b.high_water_x, 'fee_buy_sol', b.entry ->> 'fee_sol',
  'fee_sell_sol', b.exit ->> 'fee_sol', 'curve_proceeds_sol', b.exit ->> 'curve_proceeds_sol')::text
FROM meme_mature_opportunities o
LEFT JOIN meme_proposals p ON p.id = o.proposal_id
LEFT JOIN meme_paper_bets b ON b.proposal_id = o.proposal_id
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
GROUP BY p.rule_set_id, p.mint
UNION ALL
SELECT json_build_object(
  'tipo', 'estado_token', 'mint', m.mint, 'token_existe', t.mint IS NOT NULL,
  'completed_at_atual', t.completed_at, 'migrated_at_atual', t.migrated_at,
  'historico', COALESCE((
    SELECT json_agg(json_build_object(
      'id', h.id, 'coluna', h.column_name, 'antes', h.old_value, 'depois', h.new_value,
      'registrado_em', h.recorded_at) ORDER BY h.recorded_at, h.id)
    FROM meme_token_state_history h WHERE h.mint = m.mint), '[]'::json))::text
FROM (SELECT DISTINCT o.mint FROM meme_mature_opportunities o
      WHERE o.rule_set_id IN ('01994d00-6c1a-7000-8000-00000000001f',
                              '01994d00-6c1a-7000-8000-000000000020',
                              '01994d00-6c1a-7000-8000-000000000021')) m
LEFT JOIN meme_tokens t ON t.mint = m.mint;
