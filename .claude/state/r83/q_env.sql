SET statement_timeout='300s';
SELECT DISTINCT ON (st.key) st.key, sv.version, jsonb_pretty(s.supporting_features) env
FROM agent_signals s
JOIN strategy_versions sv ON sv.id = s.strategy_version_id
JOIN strategies st ON st.id = sv.strategy_id
WHERE st.key IN ('momentum','mean_reversion')
ORDER BY st.key, s.emitted_at DESC;
