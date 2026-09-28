SET statement_timeout='300s';
SELECT st.key, sv.version, sv.purpose, sv.status::text, m.market_type::text,
       o.tracking_state::text, s.direction::text,
       count(*) n, count(o.r_multiple) n_r, min(s.emitted_at) t0, max(s.emitted_at) t1
FROM agent_signals s
JOIN strategy_versions sv ON sv.id = s.strategy_version_id
JOIN strategies st ON st.id = sv.strategy_id
JOIN markets m ON m.id = s.market_id
LEFT JOIN signal_outcomes o ON o.signal_id = s.id
GROUP BY 1,2,3,4,5,6,7 ORDER BY 1,2,5,6,7;
