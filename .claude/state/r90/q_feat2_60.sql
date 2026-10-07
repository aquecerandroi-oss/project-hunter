-- R90 / H-033 — extração CEGA v2 (emenda: exchange = binance, folga 60 min, velas tardias, dispatched_at) (sem valor de desfecho): sinais long da coorte PROSPECTIVA do Lab em perpétuos
-- Binance (momentum, volume_anomaly; mean_reversion e mean_reversion_h1 só para descritivo), emitidos em
-- [2026-09-06, 2026-10-06). Por sinal: (a) velas 1m finais da janela de 1 440 min antes de observation_ts
-- (mínima, fechamentos, soma de quote_volume, maior received_at); (b) open interest de open_interest_history
-- com folga de 15 min: leitura corrente = maior bucket <= obs - 15 min; janela de 7 d terminando nela
-- (contagem e mediana de ln OI); (c) instante de inserção da leitura corrente pelo outbox (só existe desde 26/09).
-- Só a NULIDADE de r_multiple é lida, nunca o valor.
BEGIN READ ONLY;
SET LOCAL statement_timeout='1500s';
COPY (
WITH sig AS (
  SELECT s.id AS signal_id, st.key AS strategy, sv.version,
         s.market_id, m.symbol,
         (s.supporting_features->>'observation_ts')::timestamptz AS obs,
         s.emitted_at, o.tracking_state::text AS tracking_state,
         (o.r_multiple IS NOT NULL) AS has_r,
         s.supporting_features->'atr'->>'percent' AS env_atr_pct
  FROM agent_signals s
  JOIN strategy_versions sv ON sv.id = s.strategy_version_id
  JOIN strategies st ON st.id = sv.strategy_id
  JOIN markets m ON m.id = s.market_id
  JOIN exchanges e ON e.id = m.exchange_id
  LEFT JOIN signal_outcomes o ON o.signal_id = s.id
  WHERE s.direction::text = 'long'
    AND s.supporting_features->>'cohort' = 'prospective'
    AND m.market_type::text = 'perpetual' AND e.code::text = 'binance'
    AND st.key IN ('momentum','volume_anomaly','mean_reversion','mean_reversion_h1')
    AND s.emitted_at >= '2026-09-06' AND s.emitted_at < '2026-10-06'
    AND o.tracking_state::text = 'terminal'
), ev AS MATERIALIZED (
  SELECT split_part(payload->>'key', ':', 2) AS symbol,
         (payload->'payload'->>'bucket_ts')::timestamptz AS b,
         max(created_at) AS created_at, max(dispatched_at) AS dispatched_at
  FROM outbox_events
  WHERE stream = 'market.derivatives' AND split_part(payload->>'key', ':', 1) = 'binance' AND payload->'payload'->>'bucket_ts' IS NOT NULL
  GROUP BY 1, 2
)
SELECT sig.*, w.n, w.n_late, w.lo24, w.qv24, w.n_qv, w.max_recv,
       c0.close AS close_last, c240.close AS close_m240,
       cur.ts AS oi_ts, cur.open_interest AS oi_cur,
       win.n_win, win.med_ln_oi, win.t_first,
       ev.created_at AS oi_created_at, ev.dispatched_at AS oi_dispatched_at
FROM sig
CROSS JOIN LATERAL (
  SELECT count(*) AS n, count(*) FILTER (WHERE k.received_at > k.open_time + interval '6 minutes') AS n_late, min(k.low) AS lo24, sum(k.quote_volume) AS qv24, count(k.quote_volume) AS n_qv,
         max(k.received_at) AS max_recv
  FROM candles_1m k
  WHERE k.market_id = sig.market_id AND k.timeframe = '1m' AND k.is_final
    AND k.open_time >= sig.obs - interval '1440 minutes' AND k.open_time < sig.obs
) w
LEFT JOIN candles_1m c0   ON c0.market_id = sig.market_id AND c0.timeframe='1m' AND c0.is_final AND c0.open_time = sig.obs - interval '1 minute'
LEFT JOIN candles_1m c240 ON c240.market_id = sig.market_id AND c240.timeframe='1m' AND c240.is_final AND c240.open_time = sig.obs - interval '241 minutes'
LEFT JOIN LATERAL (
  SELECT h.ts, h.open_interest FROM open_interest_history h
  WHERE h.market_id = sig.market_id AND h.ts <= sig.obs - interval '60 minutes'
  ORDER BY h.ts DESC LIMIT 1
) cur ON true
LEFT JOIN LATERAL (
  SELECT count(*) AS n_win, min(h.ts) AS t_first,
         percentile_cont(0.5) WITHIN GROUP (ORDER BY ln(h.open_interest)) AS med_ln_oi
  FROM open_interest_history h
  WHERE h.market_id = sig.market_id AND h.open_interest > 0
    AND h.ts > cur.ts - interval '7 days' AND h.ts <= cur.ts
) win ON true
LEFT JOIN ev ON ev.symbol = sig.symbol AND ev.b = cur.ts
ORDER BY sig.obs
) TO STDOUT WITH (FORMAT csv, HEADER);
COMMIT;
