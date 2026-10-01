-- R86 / H-027 — extração CEGA (sem valor de desfecho): sinais long da coorte PROSPECTIVA do Lab
-- (momentum, volume_anomaly; mean_reversion v14 só para o descritivo da spot/1), com as covariáveis
-- reconstruídas das velas 1m finais que fecham em ou antes de observation_ts (como no R83):
-- janela de 1 440 min (distance_from_24h_low), fechamentos em obs−1 e obs−241 (return_4h), ATR% do envelope.
-- Só a NULIDADE de r_multiple é lida, nunca o valor.
BEGIN READ ONLY;
SET LOCAL statement_timeout='1200s';
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
         s.supporting_features->'atr'->>'timeframe' AS env_atr_tf
  FROM agent_signals s
  JOIN strategy_versions sv ON sv.id = s.strategy_version_id
  JOIN strategies st ON st.id = sv.strategy_id
  JOIN markets m ON m.id = s.market_id
  LEFT JOIN signal_outcomes o ON o.signal_id = s.id
  WHERE s.direction::text = 'long'
    AND s.supporting_features->>'cohort' = 'prospective'
    AND (st.key IN ('momentum','volume_anomaly') OR (st.key = 'mean_reversion' AND sv.version = 'v14'))
)
SELECT sig.*, w.n, w.first_open, w.last_open, w.lo24, w.max_recv,
       c0.close AS close_last, c240.close AS close_m240
FROM sig
CROSS JOIN LATERAL (
  SELECT count(*) AS n, min(k.open_time) AS first_open, max(k.open_time) AS last_open,
         min(k.low) AS lo24, max(k.received_at) AS max_recv
  FROM candles_1m k
  WHERE k.market_id = sig.market_id AND k.timeframe = '1m' AND k.is_final
    AND k.open_time >= sig.obs - interval '1440 minutes'
    AND k.open_time <  sig.obs
) w
LEFT JOIN candles_1m c0   ON c0.market_id = sig.market_id AND c0.timeframe='1m' AND c0.is_final AND c0.open_time = sig.obs - interval '1 minute'
LEFT JOIN candles_1m c240 ON c240.market_id = sig.market_id AND c240.timeframe='1m' AND c240.is_final AND c240.open_time = sig.obs - interval '241 minutes'
ORDER BY sig.obs
) TO STDOUT WITH (FORMAT csv, HEADER);
COMMIT;
