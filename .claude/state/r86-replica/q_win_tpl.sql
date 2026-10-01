SET statement_timeout='600s';
__EXPLAIN__ (
WITH sig AS (
  SELECT s.id AS signal_id, s.market_id, (s.supporting_features->>'observation_ts')::timestamptz AS obs
  FROM agent_signals s
  JOIN strategy_versions sv ON sv.id = s.strategy_version_id
  JOIN strategies st ON st.id = sv.strategy_id
  JOIN markets m ON m.id = s.market_id
  JOIN signal_outcomes o ON o.signal_id = s.id
  WHERE s.emitted_at >= '__A__' AND s.emitted_at < '__B__'
    AND s.supporting_features->>'cohort' = 'prospective'
    AND m.market_type::text = 'perpetual' AND s.direction::text = 'long'
    AND o.tracking_state::text = 'terminal'
    AND (st.key IN ('momentum','volume_anomaly') OR (st.key = 'mean_reversion' AND sv.version = 'v14'))
)
SELECT sig.signal_id, w.n, w.n_distinct, w.first_open, w.last_open, w.lo, w.max_recv,
       (SELECT k.close FROM candles_1m k WHERE k.market_id=sig.market_id AND k.timeframe='1m' AND k.is_final AND k.open_time = sig.obs - interval '1 minute') AS c_m1,
       (SELECT k.close FROM candles_1m k WHERE k.market_id=sig.market_id AND k.timeframe='1m' AND k.is_final AND k.open_time = sig.obs - interval '241 minutes') AS c_m241
FROM sig
CROSS JOIN LATERAL (
  SELECT count(*) AS n, count(DISTINCT k.open_time) AS n_distinct, min(k.open_time) AS first_open, max(k.open_time) AS last_open,
         min(k.low) AS lo, max(k.received_at) AS max_recv
  FROM candles_1m k
  WHERE k.market_id = sig.market_id AND k.timeframe = '1m' AND k.is_final
    AND k.open_time >= sig.obs - interval '1440 minutes' AND k.open_time < sig.obs
) w
) __TAIL__
