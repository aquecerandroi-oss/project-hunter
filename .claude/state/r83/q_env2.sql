SET statement_timeout='300s';
SELECT st.key, sv.version, s.supporting_features->>'cohort' cohort,
  count(*) n,
  count(*) FILTER (WHERE s.supporting_features ? 'observation_ts') has_obs,
  string_agg(DISTINCT (SELECT string_agg(f->>'name', ',' ORDER BY f->>'name') FROM jsonb_array_elements(s.supporting_features->'features') f), ' | ') feats
FROM agent_signals s
JOIN strategy_versions sv ON sv.id = s.strategy_version_id
JOIN strategies st ON st.id = sv.strategy_id
JOIN markets m ON m.id=s.market_id
WHERE m.market_type='perpetual'
GROUP BY 1,2,3 ORDER BY 1,2,3;
SELECT DISTINCT jsonb_object_keys(s.supporting_features) k FROM agent_signals s;
