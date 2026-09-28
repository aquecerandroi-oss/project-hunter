SET statement_timeout='100s';
WITH s AS (SELECT s.market_id, (s.supporting_features->>'observation_ts')::timestamptz obs, s.emitted_at FROM agent_signals s
 JOIN strategy_versions sv ON sv.id=s.strategy_version_id WHERE sv.version='v3' AND s.emitted_at > '2026-09-20' LIMIT 3)
SELECT s.obs, s.emitted_at, fs.ts, fs.features->>'ts' computed, fs.feature_set_version, fs.features->'values'->'distance_from_24h_high' dh, fs.features->'provenance'->'candles:1m' prov
FROM s JOIN LATERAL (SELECT * FROM feature_snapshots f WHERE f.market_id=s.market_id AND f.ts BETWEEN s.obs - interval '10 min' AND s.obs + interval '2 min' ORDER BY f.ts) fs ON true;
