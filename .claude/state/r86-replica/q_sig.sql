-- r86-replica: população (com desfecho; replicação depois do registro da H-027).
SET statement_timeout='300s';
COPY (
SELECT s.id AS signal_id, st.key AS strategy, sv.version, s.market_id, m.symbol, e.code AS exchange,
       (s.supporting_features->>'observation_ts') AS obs, s.emitted_at,
       s.supporting_features->'atr'->>'percent' AS atr_pct,
       s.supporting_features->'atr'->>'timeframe' AS atr_tf,
       o.r_multiple, o.meta->>'r_ex_funding' AS r_ex_funding, o.meta->>'r_net_reason' AS r_net_reason
FROM agent_signals s
JOIN strategy_versions sv ON sv.id = s.strategy_version_id
JOIN strategies st ON st.id = sv.strategy_id
JOIN markets m ON m.id = s.market_id
JOIN exchanges e ON e.id = m.exchange_id
JOIN signal_outcomes o ON o.signal_id = s.id
WHERE s.emitted_at >= '2026-09-06T00:00:00Z' AND s.emitted_at < '2026-10-01T00:00:00Z'
  AND s.supporting_features->>'cohort' = 'prospective'
  AND m.market_type::text = 'perpetual' AND s.direction::text = 'long'
  AND o.tracking_state::text = 'terminal'
  AND (st.key IN ('momentum','volume_anomaly') OR (st.key = 'mean_reversion' AND sv.version = 'v14'))
ORDER BY s.emitted_at, s.id
) TO STDOUT WITH (FORMAT csv, HEADER);
