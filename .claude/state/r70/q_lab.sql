SET statement_timeout='900s';
COPY (
WITH sig AS (
  SELECT s.id AS signal_id, s.market_id, m.symbol,
         s.emitted_at AS t, to_char(s.emitted_at, 'YYYY-MM-DD') AS dia,
         o.r_multiple, o.result::text AS result,
         (SELECT f->>'value' FROM jsonb_array_elements(s.supporting_features->'features') f
           WHERE f->>'name' = 'volume_ratio_5m' AND (f->>'available')::bool) AS env_vr5,
         (SELECT f->>'value' FROM jsonb_array_elements(s.supporting_features->'features') f
           WHERE f->>'name' = 'return_4h' AND (f->>'available')::bool) AS env_ret4h,
         (SELECT f->>'value' FROM jsonb_array_elements(s.supporting_features->'features') f
           WHERE f->>'name' = 'momentum_15m' AND (f->>'available')::bool) AS env_mom15
  FROM agent_signals s
  JOIN signal_outcomes o ON o.signal_id = s.id
  JOIN markets m ON m.id = s.market_id
  WHERE o.tracking_state = 'terminal' AND o.r_multiple IS NOT NULL
    AND s.emitted_at >= TIMESTAMPTZ '2026-09-06 19:00+00'
),
snap AS (
  SELECT g.signal_id, g.snap_as_of, g.snap_computed_at, g.snap_tape,
         g.mom15, g.mom15_q, g.ret4h, g.ret4h_q, g.rv5, g.rv5_q, g.atr_pct
  FROM sig CROSS JOIN LATERAL (
    SELECT sig.signal_id,
           fs.ts AS snap_as_of,
           (fs.features->>'ts')::timestamptz AS snap_computed_at,
           (fs.features->'provenance'->'candles:1m'->>'ts')::timestamptz AS snap_tape,
           fs.features->'values'->'momentum_15m'->>'value' AS mom15,
           fs.features->'values'->'momentum_15m'->>'quality' AS mom15_q,
           fs.features->'values'->'return_4h'->>'value' AS ret4h,
           fs.features->'values'->'return_4h'->>'quality' AS ret4h_q,
           fs.features->'values'->'relative_volume_5m'->>'value' AS rv5,
           fs.features->'values'->'relative_volume_5m'->>'quality' AS rv5_q,
           fs.features->'values'->'atr_14_pct'->>'value' AS atr_pct
    FROM feature_snapshots fs
    WHERE fs.market_id = sig.market_id
      AND fs.ts <= sig.t
      AND (fs.features->>'ts')::timestamptz <= sig.t
      AND fs.ts > sig.t - interval '10 minutes'
    ORDER BY fs.ts DESC
    LIMIT 1
  ) g
),
tk AS (
  SELECT c.signal_id, c.nbars, c.taker_buy, c.vol, c.last_close, c.max_recv
  FROM sig CROSS JOIN LATERAL (
    SELECT sig.signal_id,
           count(*) AS nbars,
           sum(k.taker_buy_volume) AS taker_buy,
           sum(k.volume) AS vol,
           max(k.open_time) + interval '1 minute' AS last_close,
           max(k.received_at) AS max_recv
    FROM candles_1m k
    WHERE k.market_id = sig.market_id
      AND k.timeframe = '1m' AND k.is_final
      AND k.open_time <= date_trunc('minute', sig.t) - interval '1 minute'
      AND k.open_time >  date_trunc('minute', sig.t) - interval '6 minutes'
      AND k.received_at <= sig.t
      AND k.taker_buy_volume IS NOT NULL
  ) c
)
SELECT sig.signal_id, sig.symbol, sig.t, sig.dia, sig.r_multiple, sig.result,
       sig.env_vr5, sig.env_ret4h, sig.env_mom15,
       snap.snap_as_of, snap.snap_computed_at, snap.snap_tape,
       snap.mom15, snap.mom15_q, snap.ret4h, snap.ret4h_q, snap.rv5, snap.rv5_q, snap.atr_pct,
       tk.nbars, tk.taker_buy, tk.vol, tk.last_close, tk.max_recv
FROM sig
LEFT JOIN snap ON snap.signal_id = sig.signal_id
LEFT JOIN tk   ON tk.signal_id   = sig.signal_id
ORDER BY sig.t
) TO STDOUT WITH (FORMAT csv, HEADER);
