-- h036 — contagem cega por semana ISO com os filtros da população (long, Binance, perpétuo, prospectiva), sinais
-- elegíveis (não no_entry) e dias com sinal; sem nenhum valor de desfecho. Semanas parciais marcadas.
BEGIN READ ONLY;
SET LOCAL statement_timeout='300s';
WITH v AS (SELECT sv.id FROM strategy_versions sv JOIN strategies st ON st.id = sv.strategy_id
           WHERE st.key = 'mean_reversion' AND sv.version = 'v14')
SELECT date_trunc('week', a.emitted_at)::date AS semana,
       count(*) AS sinais, count(*) FILTER (WHERE o.tracking_state::text <> 'no_entry') AS elegiveis,
       count(DISTINCT a.emitted_at::date) AS dias_com_sinal,
       CASE WHEN date_trunc('week', a.emitted_at) < '2026-09-14' OR date_trunc('week', a.emitted_at) >= '2026-10-05'
            THEN 'parcial' ELSE 'completa' END AS semana_tipo
FROM agent_signals a JOIN v ON v.id = a.strategy_version_id JOIN markets m ON m.id = a.market_id
JOIN exchanges e ON e.id = m.exchange_id LEFT JOIN signal_outcomes o ON o.signal_id = a.id
WHERE a.emitted_at < '2026-10-07 06:07:00+00' AND a.direction::text = 'long' AND m.market_type::text = 'perpetual'
  AND e.code::text = 'binance' AND a.supporting_features->>'cohort' = 'prospective'
GROUP BY 1, 5 ORDER BY 1;
COMMIT;
