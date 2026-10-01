SET statement_timeout='60s';
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='markets' ORDER BY ordinal_position;
SELECT st.key, sv.version, s.supporting_features->>'cohort' cohort, m.market_type::text, s.direction::text, o.tracking_state::text, count(*)
FROM agent_signals s JOIN strategy_versions sv ON sv.id=s.strategy_version_id JOIN strategies st ON st.id=sv.strategy_id
JOIN markets m ON m.id=s.market_id LEFT JOIN signal_outcomes o ON o.signal_id=s.id
WHERE s.emitted_at >= '2026-09-06' AND s.emitted_at < '2026-10-01' AND st.key IN ('momentum','volume_anomaly','mean_reversion')
GROUP BY 1,2,3,4,5,6 ORDER BY 1,2,3,4,5,6;
