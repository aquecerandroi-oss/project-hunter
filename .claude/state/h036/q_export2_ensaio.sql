-- h036 export cego (só spread) [2026-09-09T19:37:36+00:00, 2026-10-07T00:00:00+00:00) — gen_export2.py; só leitura
BEGIN READ ONLY;
SET LOCAL statement_timeout='600s';
COPY (
WITH v AS (SELECT sv.id FROM strategy_versions sv JOIN strategies st ON st.id = sv.strategy_id
           WHERE st.key = 'mean_reversion' AND sv.version = 'v14'),
sg AS (SELECT a.id, a.market_id, a.emitted_at, m.tick_size FROM agent_signals a JOIN v ON v.id = a.strategy_version_id
       JOIN markets m ON m.id = a.market_id JOIN exchanges e ON e.id = m.exchange_id
       WHERE a.emitted_at >= '2026-09-09T19:37:36+00:00' AND a.emitted_at < '2026-10-07T00:00:00+00:00' AND a.direction::text = 'long'
         AND m.market_type::text = 'perpetual' AND e.code::text = 'binance'
         AND a.supporting_features->>'cohort' = 'prospective')
SELECT 'serie' AS tipo, sg.id AS signal_id, ms.ts, ms.spread_pct, NULL::numeric AS mediana_7d,
       NULL::bigint AS n_snap_7d, sg.tick_size
FROM sg JOIN market_snapshots ms ON ms.market_id = sg.market_id
 AND ms.ts >= date_trunc('minute', sg.emitted_at) AND ms.ts <= sg.emitted_at + interval '250 minutes'
UNION ALL
SELECT 'mediana_7d', sg.id, NULL, NULL, w.med, w.n, sg.tick_size
FROM sg CROSS JOIN LATERAL (
  SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY ms.spread_pct) AS med, count(ms.spread_pct) AS n
  FROM market_snapshots ms WHERE ms.market_id = sg.market_id
   AND ms.ts >= sg.emitted_at - interval '7 days' AND ms.ts < sg.emitted_at) w
ORDER BY 2, 1, 3
) TO STDOUT WITH (FORMAT csv, HEADER);
COMMIT;
