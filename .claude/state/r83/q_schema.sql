\d candles_1m
SELECT fs.ts, fs.features->>'ts' computed, fs.features->'values'->'distance_from_24h_high' dh, fs.features->'provenance'->'candles:1m' prov
FROM feature_snapshots fs WHERE fs.ts = TIMESTAMPTZ '2026-09-20 12:15+00' LIMIT 2;
