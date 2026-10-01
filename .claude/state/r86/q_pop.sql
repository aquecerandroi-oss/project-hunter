-- R86 / H-027 — contagem CEGA (sem valor de desfecho): continuação por estratégia/versão/coorte/estado.
BEGIN READ ONLY;
SET LOCAL statement_timeout='120s';
SELECT st.key, sv.version, sv.purpose, sv.status::text, m.market_type::text,
       s.supporting_features->>'cohort' cohort, o.tracking_state::text, s.direction::text,
       count(*) n, count(o.r_multiple) n_r,
       min(s.emitted_at) t0, max(s.emitted_at) t1,
       count(DISTINCT (s.emitted_at AT TIME ZONE 'UTC')::date) dias
FROM agent_signals s
JOIN strategy_versions sv ON sv.id = s.strategy_version_id
JOIN strategies st ON st.id = sv.strategy_id
JOIN markets m ON m.id = s.market_id
LEFT JOIN signal_outcomes o ON o.signal_id = s.id
WHERE st.key IN ('momentum','volume_anomaly')
GROUP BY 1,2,3,4,5,6,7,8 ORDER BY 1,2,5,6,7,8;
COMMIT;
