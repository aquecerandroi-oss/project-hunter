-- R83 — validação da reconstrução contra feature_snapshots (produção) no mesmo minuto obs. Sem desfecho.
SET statement_timeout='1200s';
COPY (
SELECT s.id AS signal_id, fs.ts AS snap_ts, (fs.features->>'ts')::timestamptz AS snap_computed,
       (fs.features->'provenance'->'candles:1m'->>'ts')::timestamptz AS snap_candle_ts,
       fs.features->'values'->'distance_from_24h_high'->>'value' AS s_dh,
       fs.features->'values'->'distance_from_24h_low'->>'value'  AS s_dl,
       fs.features->'values'->'return_15m'->>'value' AS s_r15,
       fs.features->'values'->'return_4h'->>'value' AS s_r4h,
       fs.features->'values'->'momentum_15m'->>'value' AS s_mom15,
       fs.features->'values'->'atr_14_pct'->>'value' AS s_atr
FROM agent_signals s
JOIN signal_outcomes o ON o.signal_id = s.id AND o.tracking_state = 'terminal'
JOIN markets m ON m.id = s.market_id AND m.market_type = 'perpetual'
JOIN feature_snapshots fs ON fs.market_id = s.market_id
     AND fs.ts = (s.supporting_features->>'observation_ts')::timestamptz
WHERE s.supporting_features->>'cohort' = 'prospective'
  AND (s.supporting_features->>'observation_ts')::timestamptz >= TIMESTAMPTZ '2026-09-06 18:17+00'
) TO STDOUT WITH (FORMAT csv, HEADER);
