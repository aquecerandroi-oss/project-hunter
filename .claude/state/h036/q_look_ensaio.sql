-- h036 consulta ENSAIO (coorte exposta) [2026-09-09T19:37:36+00:00, 2026-10-07T00:00:00+00:00) — gen_look.py
BEGIN READ ONLY;
SET LOCAL statement_timeout='600s';
COPY (
WITH v AS (SELECT sv.id FROM strategy_versions sv JOIN strategies st ON st.id = sv.strategy_id
           WHERE st.key = 'mean_reversion' AND sv.version = 'v14')
SELECT a.id AS signal_id, a.emitted_at, coalesce(o.tracking_state::text, 'sem_linha') AS tracking_state,
       o.result::text AS result, o.entry_ts, (o.meta->'progress'->>'exit_bar_open') AS xbo,
       (o.meta->'progress'->>'exit_at_open') AS x_at_open, o.meta->'progress'->>'exit_bar_high' AS x_high,
       o.virtual_targets->>0 AS target1, o.meta->'progress'->>'entry' AS entry_c,
       o.meta->'progress'->>'exit_base' AS exit_base, o.virtual_stop AS stop, m.symbol,
       o.meta->'funding'->>'per_unit' AS funding_per_unit, o.meta->'assumed_costs'->>'spread_bps' AS spread_bps,
       o.meta->'assumed_costs'->>'slippage_bps' AS slippage_bps
FROM agent_signals a JOIN v ON v.id = a.strategy_version_id JOIN markets m ON m.id = a.market_id
JOIN exchanges e ON e.id = m.exchange_id LEFT JOIN signal_outcomes o ON o.signal_id = a.id
WHERE a.emitted_at >= '2026-09-09T19:37:36+00:00' AND a.emitted_at < '2026-10-07T00:00:00+00:00' AND a.direction::text = 'long'
  AND m.market_type::text = 'perpetual' AND e.code::text = 'binance'
  AND a.supporting_features->>'cohort' = 'prospective' AND (o.exit_ts <= '2026-10-07 06:07:00+00' OR o.tracking_state::text = 'no_entry')
ORDER BY a.emitted_at
) TO STDOUT WITH (FORMAT csv, HEADER);
COMMIT;
