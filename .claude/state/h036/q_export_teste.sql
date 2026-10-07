-- h036 export cego [2026-10-06T00:00:00Z, 2026-10-07T06:07:00Z) — gerado por gen_export.py; só leitura
BEGIN READ ONLY;
SET LOCAL statement_timeout='600s';
COPY (
WITH v AS (SELECT sv.id FROM strategy_versions sv JOIN strategies st ON st.id = sv.strategy_id
           WHERE st.key = 'mean_reversion' AND sv.version = 'v14'),
sg AS (SELECT a.id, a.market_id, a.emitted_at FROM agent_signals a JOIN v ON v.id = a.strategy_version_id
       JOIN markets m ON m.id = a.market_id JOIN exchanges e ON e.id = m.exchange_id
       WHERE a.emitted_at >= '2026-10-06T00:00:00Z' AND a.emitted_at < '2026-10-07T06:07:00Z' AND a.direction::text = 'long'
         AND m.market_type::text = 'perpetual' AND e.code::text = 'binance'
         AND a.supporting_features->>'cohort' = 'prospective')
SELECT 'serie' AS tipo, sg.id AS signal_id, ms.ts, ms.bid, ms.ask, ms.spread_pct, NULL::numeric AS mediana_7d
FROM sg JOIN market_snapshots ms ON ms.market_id = sg.market_id
 AND ms.ts >= date_trunc('minute', sg.emitted_at) AND ms.ts <= sg.emitted_at + interval '250 minutes'
UNION ALL
SELECT 'mediana_7d', sg.id, NULL, NULL, NULL, NULL,
       (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY ms.spread_pct) FROM market_snapshots ms
        WHERE ms.market_id = sg.market_id AND ms.ts >= sg.emitted_at - interval '7 days' AND ms.ts < sg.emitted_at)
FROM sg
ORDER BY 2, 1, 3
) TO STDOUT WITH (FORMAT csv, HEADER);
COMMIT;
