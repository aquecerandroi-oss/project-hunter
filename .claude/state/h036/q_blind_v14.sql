-- h036 — inventário cego da mean_reversion v14 (nenhum valor de desfecho: só direção, tipo de mercado, contagem por dia
-- e estado de rastreio), sinais emitidos antes do corte de exposição 2026-10-07 06:07Z.
BEGIN READ ONLY;
SET LOCAL statement_timeout='300s';
WITH v AS (SELECT sv.id FROM strategy_versions sv JOIN strategies st ON st.id = sv.strategy_id
           WHERE st.key = 'mean_reversion' AND sv.version = 'v14')
SELECT a.direction::text, m.market_type::text, e.code::text, a.supporting_features->>'cohort' AS cohort,
       coalesce(o.tracking_state::text, 'sem_linha') AS estado, count(*)
FROM agent_signals a JOIN v ON v.id = a.strategy_version_id JOIN markets m ON m.id = a.market_id
JOIN exchanges e ON e.id = m.exchange_id LEFT JOIN signal_outcomes o ON o.signal_id = a.id
WHERE a.emitted_at < '2026-10-07 06:07:00+00' GROUP BY 1,2,3,4,5 ORDER BY 1,2,3,4,5;
WITH v AS (SELECT sv.id FROM strategy_versions sv JOIN strategies st ON st.id = sv.strategy_id
           WHERE st.key = 'mean_reversion' AND sv.version = 'v14')
SELECT date_trunc('week', a.emitted_at)::date AS semana, count(*) AS sinais, count(DISTINCT a.emitted_at::date) AS dias_com_sinal
FROM agent_signals a JOIN v ON v.id = a.strategy_version_id
WHERE a.emitted_at < '2026-10-07 06:07:00+00' AND a.supporting_features->>'cohort' = 'prospective'
GROUP BY 1 ORDER BY 1;
COMMIT;
