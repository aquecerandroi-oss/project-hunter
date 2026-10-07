-- R90 — desfechos (lidos só depois do pré-registro 04:51:02Z, da emenda 05:15:31Z e da lista congelada 05:18:27Z).
BEGIN READ ONLY;
SET LOCAL statement_timeout='300s';
COPY (
SELECT o.signal_id, o.r_multiple, o.meta->>'r_ex_funding' AS r_ex_funding, o.result::text AS result,
       o.exit_ts, now() AS read_at
FROM signal_outcomes o
JOIN agent_signals s ON s.id = o.signal_id
JOIN strategy_versions sv ON sv.id = s.strategy_version_id
JOIN strategies st ON st.id = sv.strategy_id
JOIN markets m ON m.id = s.market_id
JOIN exchanges e ON e.id = m.exchange_id
WHERE o.tracking_state = 'terminal' AND s.direction::text = 'long'
  AND s.supporting_features->>'cohort' = 'prospective'
  AND m.market_type::text = 'perpetual' AND e.code::text = 'binance'
  AND st.key IN ('momentum','volume_anomaly','mean_reversion','mean_reversion_h1')
  AND s.emitted_at >= '2026-09-06' AND s.emitted_at < '2026-10-06'
ORDER BY o.signal_id
) TO STDOUT WITH (FORMAT csv, HEADER);
COMMIT;
