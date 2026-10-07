-- R90 / H-033 — contagem CEGA (sem valor de desfecho): sinais do Lab por estratégia/versão/tipo/coorte/estado/direção.
BEGIN READ ONLY;
SET LOCAL statement_timeout='180s';
SELECT st.key, m.market_type::text mt, s.supporting_features->>'cohort' cohort, o.tracking_state::text ts, s.direction::text dir,
       count(*) n, count(o.r_multiple) n_r, count(DISTINCT s.market_id) mk,
       min(s.emitted_at)::date t0, max(s.emitted_at)::date t1,
       count(DISTINCT (s.emitted_at AT TIME ZONE 'UTC')::date) dias,
       string_agg(DISTINCT sv.version, ',') vs
FROM agent_signals s
JOIN strategy_versions sv ON sv.id = s.strategy_version_id
JOIN strategies st ON st.id = sv.strategy_id
JOIN markets m ON m.id = s.market_id
LEFT JOIN signal_outcomes o ON o.signal_id = s.id
WHERE s.emitted_at >= '2026-09-06' AND s.emitted_at < '2026-10-07'
GROUP BY 1,2,3,4,5 ORDER BY 1,2,3,4,5;
COMMIT;
