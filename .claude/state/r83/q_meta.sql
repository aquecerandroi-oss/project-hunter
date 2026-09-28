SET statement_timeout='200s';
SELECT k, count(*) FROM signal_outcomes o, jsonb_object_keys(o.meta) k WHERE o.tracking_state='terminal' GROUP BY 1 ORDER BY 2 DESC;
SELECT o.meta->>'r_net_reason' reason, m.market_type::text, count(*) FROM signal_outcomes o JOIN agent_signals s ON s.id=o.signal_id JOIN markets m ON m.id=s.market_id WHERE o.tracking_state='terminal' AND o.r_multiple IS NULL GROUP BY 1,2;
SELECT jsonb_pretty(s.supporting_features->'atr') atr, jsonb_pretty(s.supporting_features->'assumed_costs') c, s.supporting_features->>'decision_at' d, s.supporting_features->>'observation_ts' o FROM agent_signals s ORDER BY emitted_at DESC LIMIT 1;
