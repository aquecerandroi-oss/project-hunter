-- lab-cost-sweep — inventário: sinais do Lab por estratégia/versão/tipo/coorte/estado (sem valores de R).
BEGIN READ ONLY;
SET LOCAL statement_timeout='180s';
SELECT st.key, sv.version, m.market_type::text mt, e.code::text ex, s.supporting_features->>'cohort' cohort,
       o.meta->>'purpose' purpose, o.tracking_state::text ts, s.direction::text dir,
       count(*) n, count(o.r_multiple) n_r, count(DISTINCT s.market_id) mk,
       min(s.emitted_at)::date t0, max(s.emitted_at)::date t1,
       count(DISTINCT (s.emitted_at AT TIME ZONE 'UTC')::date) dias
FROM agent_signals s
JOIN strategy_versions sv ON sv.id = s.strategy_version_id
JOIN strategies st ON st.id = sv.strategy_id
JOIN markets m ON m.id = s.market_id
JOIN exchanges e ON e.id = m.exchange_id
LEFT JOIN signal_outcomes o ON o.signal_id = s.id
GROUP BY 1,2,3,4,5,6,7,8 ORDER BY 1,2,3,4,5,6,7,8;
COMMIT;
