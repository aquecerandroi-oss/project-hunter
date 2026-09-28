SET statement_timeout='100s';
SELECT fs.market_id, fs.ts, fs.features->>'ts' computed, fs.features->'values'->'distance_from_24h_high' dh, fs.features->'values'->'return_4h' r4, fs.features->'provenance'->'candles:1m' prov
FROM feature_snapshots fs WHERE fs.ts >= TIMESTAMPTZ '2026-09-20 12:15+00' AND fs.ts < TIMESTAMPTZ '2026-09-20 12:16+00' LIMIT 2;
