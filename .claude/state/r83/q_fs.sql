SET statement_timeout='300s';
SELECT min(ts), max(ts), count(*) FROM feature_snapshots;
SELECT min(open_time), max(open_time) FROM candles_1m;
SELECT fs.ts, fs.features->>'ts' computed, fs.features->'values'->'distance_from_24h_high' dh, fs.features->'values'->'distance_from_24h_low' dl, fs.features->'provenance'->'candles:1m' prov
FROM feature_snapshots fs ORDER BY fs.ts DESC LIMIT 2;
