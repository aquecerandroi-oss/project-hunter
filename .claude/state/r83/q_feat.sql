-- R83 / H-023 — extração CEGA (sem valor de desfecho): features no instante do sinal.
-- Janela da produção (features/price.py:106, DistanceFromExtreme v1): as 1 440 velas 1m
-- is_final contíguas que fecham em ou antes de observation_ts (source_bar_close).
-- Só se exige que exista R (nulidade), nunca se lê o valor.
SET statement_timeout='3000s';
COPY (
WITH sig AS (
  SELECT s.id AS signal_id, st.key AS strategy, sv.version, sv.purpose,
         s.supporting_features->>'cohort' AS cohort,
         s.market_id, m.symbol, m.market_type::text AS market_type,
         (s.supporting_features->>'observation_ts')::timestamptz AS obs,
         s.emitted_at, o.tracking_state::text AS tracking_state,
         (o.r_multiple IS NOT NULL) AS has_r,
         o.meta->>'r_net_reason' AS r_net_reason,
         s.supporting_features->'atr'->>'percent' AS env_atr_pct,
         s.supporting_features->'atr'->>'timeframe' AS env_atr_tf,
         (SELECT f->>'value' FROM jsonb_array_elements(s.supporting_features->'features') f
           WHERE f->>'name' = 'return_15m' AND (f->>'available')::bool) AS env_ret15,
         (SELECT f->>'value' FROM jsonb_array_elements(s.supporting_features->'features') f
           WHERE f->>'name' = 'zscore_15m' AND (f->>'available')::bool) AS env_z15,
         (SELECT f->>'value' FROM jsonb_array_elements(s.supporting_features->'features') f
           WHERE f->>'name' IN ('relative_volume_15m','volume_ratio_5m','rvol_15m') AND (f->>'available')::bool LIMIT 1) AS env_rvol,
         (SELECT f->>'value' FROM jsonb_array_elements(s.supporting_features->'features') f
           WHERE f->>'name' = 'distance_from_24h_high' AND (f->>'available')::bool) AS env_dh
  FROM agent_signals s
  JOIN strategy_versions sv ON sv.id = s.strategy_version_id
  JOIN strategies st ON st.id = sv.strategy_id
  JOIN markets m ON m.id = s.market_id
  JOIN signal_outcomes o ON o.signal_id = s.id
  WHERE o.tracking_state = 'terminal' AND s.direction::text = 'long'
)
SELECT sig.*, w.n, w.first_open, w.last_open, w.hi24, w.lo24, w.max_recv,
       c0.close AS close_last, c15.close AS close_m15, c60.close AS close_m60, c240.close AS close_m240
FROM sig
CROSS JOIN LATERAL (
  SELECT count(*) AS n, min(k.open_time) AS first_open, max(k.open_time) AS last_open,
         max(k.high) AS hi24, min(k.low) AS lo24, max(k.received_at) AS max_recv
  FROM candles_1m k
  WHERE k.market_id = sig.market_id AND k.timeframe = '1m' AND k.is_final
    AND k.open_time >= sig.obs - interval '1440 minutes'
    AND k.open_time <  sig.obs
) w
LEFT JOIN candles_1m c0   ON c0.market_id = sig.market_id AND c0.timeframe='1m' AND c0.is_final AND c0.open_time = sig.obs - interval '1 minute'
LEFT JOIN candles_1m c15  ON c15.market_id = sig.market_id AND c15.timeframe='1m' AND c15.is_final AND c15.open_time = sig.obs - interval '16 minutes'
LEFT JOIN candles_1m c60  ON c60.market_id = sig.market_id AND c60.timeframe='1m' AND c60.is_final AND c60.open_time = sig.obs - interval '61 minutes'
LEFT JOIN candles_1m c240 ON c240.market_id = sig.market_id AND c240.timeframe='1m' AND c240.is_final AND c240.open_time = sig.obs - interval '241 minutes'
ORDER BY sig.obs
) TO STDOUT WITH (FORMAT csv, HEADER);
