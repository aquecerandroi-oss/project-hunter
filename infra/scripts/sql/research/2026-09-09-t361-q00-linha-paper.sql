-- T3.61 — estado da linha `paper` antes de qualquer escrita (leitura pura).
-- Rodar: docker exec -i hunter-postgres-1 psql -U hunter -d hunter -X -q -f - < este arquivo
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

\echo '== 0. read_at =='
SELECT now() AS read_at_utc, now() AT TIME ZONE 'America/Sao_Paulo' AS read_at_brt;

\echo '== 1. catalogo status x purpose =='
SELECT status::text, purpose::text, count(*) AS versoes
  FROM strategy_versions GROUP BY 1,2 ORDER BY 1,2;

\echo '== 2. roster vivo (status active) =='
SELECT s.key || ' ' || v.version AS versao, v.purpose::text, v.status::text,
       v.activated_at, v.eligibility_policy
  FROM strategy_versions v JOIN strategies s ON s.id = v.strategy_id
 WHERE v.status = 'active' ORDER BY s.key, length(v.version), v.version;

\echo '== 3. as duas versoes do ato: momentum v3 (linha paper) e mean_reversion v6 =='
SELECT v.id, s.key || ' ' || v.version AS versao, v.status::text, v.purpose::text,
       v.activated_at, v.params_format, v.code_ref, left(v.changelog, 120) AS changelog_ini
  FROM strategy_versions v JOIN strategies s ON s.id = v.strategy_id
 WHERE (s.key='momentum' AND v.version='v3') OR (s.key='mean_reversion' AND v.version='v6');

\echo '== 4. exposicao aberta da linha paper (a mesma consulta de open_paper_exposure) =='
SELECT s.key || ' ' || v.version AS versao,
       (SELECT count(*) FROM shadow_episodes e
         WHERE e.strategy_version_id = v.id AND e.open_outcome_signal_id IS NOT NULL) AS slots_abertos,
       (SELECT count(DISTINCT p.id) FROM positions p
          JOIN orders o ON o.proposal_id = (p.metadata->>'proposal_id')::uuid
          JOIN trade_proposals tp ON tp.id = o.proposal_id
          JOIN agents a ON a.id = tp.agent_id
         WHERE a.strategy_version_id = v.id AND p.status <> 'closed' AND NOT p.is_residual) AS posicoes_abertas
  FROM strategy_versions v JOIN strategies s ON s.id = v.strategy_id
 WHERE v.purpose = 'paper' AND v.status = 'active';

\echo '== 5. o vinculo agents (quem a ponte seguiria) =='
SELECT a.id AS agent_id, a.name, a.status::text, a.allowed_directions,
       s.key || ' ' || v.version AS versao, v.purpose::text, a.portfolio_id, a.deleted_at
  FROM agents a JOIN strategy_versions v ON v.id = a.strategy_version_id
  JOIN strategies s ON s.id = v.strategy_id ORDER BY a.created_at;

\echo '== 6. versoes de mean_reversion (qual v<n> nasceria de --paper-line) =='
SELECT v.version, v.status::text, v.purpose::text, v.activated_at IS NOT NULL AS congelada
  FROM strategy_versions v JOIN strategies s ON s.id = v.strategy_id
 WHERE s.key = 'mean_reversion' ORDER BY length(v.version), v.version;

\echo '== 7. merito medido: mean_reversion v6 vs momentum v3, por coorte =='
WITH pop AS (
  SELECT s.key || ' ' || v.version AS versao,
         CASE WHEN sig.supporting_features->>'cohort' LIKE 'replay:%' THEN 'replay' ELSE 'prospective' END AS coorte,
         o.r_multiple
    FROM signal_outcomes o
    JOIN agent_signals sig ON sig.id = o.signal_id
    JOIN strategy_versions v ON v.id = sig.strategy_version_id
    JOIN strategies s ON s.id = v.strategy_id
   WHERE o.r_multiple IS NOT NULL AND o.tracking_state = 'terminal'
     AND ((s.key='mean_reversion' AND v.version='v6') OR (s.key='momentum' AND v.version='v3')))
SELECT versao, coorte, count(*) AS n,
       round(avg(r_multiple), 4) AS expectancia_R,
       round(sum(r_multiple), 2) AS soma_R,
       count(*) FILTER (WHERE r_multiple > 0) AS ganhos,
       round(sum(r_multiple) FILTER (WHERE r_multiple > 0)
             / NULLIF(-sum(r_multiple) FILTER (WHERE r_multiple < 0), 0), 3) AS profit_factor
  FROM pop GROUP BY 1,2 ORDER BY 1,2;

\echo '== 8. ponte: shadow_outbox e propostas (autonomia desligada) =='
SELECT count(*) AS outbox_total,
       count(*) FILTER (WHERE dispatched_at IS NULL) AS pendentes,
       max(created_at) AS ultimo_evento
  FROM shadow_outbox;
SELECT count(*) AS propostas_total, max(created_at) AS ultima_proposta FROM trade_proposals;
SELECT count(*) AS ordens, (SELECT count(*) FROM fills) AS fills, (SELECT count(*) FROM positions) AS posicoes FROM orders;

COMMIT;
