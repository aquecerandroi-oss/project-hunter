-- lab-cost-sweep — desfechos terminais de TODO o Lab (prospectivo e replay), com os insumos para recompor o R
-- sob outro custo: abertura com custo (progress.entry), base de saída (progress.exit_base), stop, custos assumidos
-- gravados na decisão, funding por unidade gravado, R do Lab (r_multiple) e r_ex_funding. Só leitura.
BEGIN READ ONLY;
SET LOCAL statement_timeout='300s';
COPY (
SELECT o.signal_id, st.key AS strategy, sv.version, m.market_type::text AS mt, m.symbol,
       s.supporting_features->>'cohort' AS cohort, o.meta->>'purpose' AS purpose,
       s.emitted_at, o.entry_ts, o.exit_ts, o.result::text AS result,
       o.virtual_stop AS stop, o.meta->'progress'->>'entry' AS entry_c, o.meta->'progress'->>'exit_base' AS exit_base,
       o.exit_price, o.r_multiple, o.meta->>'r_ex_funding' AS r_ex_funding, o.meta->>'r_net_reason' AS r_net_reason,
       o.meta->'funding'->>'per_unit' AS funding_per_unit,
       o.meta->'assumed_costs'->>'spread_bps' AS spread_bps, o.meta->'assumed_costs'->>'slippage_bps' AS slippage_bps,
       o.meta->'assumed_costs'->>'fee_bps' AS fee_bps, o.meta->>'reference_price' AS reference_price
FROM signal_outcomes o
JOIN agent_signals s ON s.id = o.signal_id
JOIN strategy_versions sv ON sv.id = s.strategy_version_id
JOIN strategies st ON st.id = sv.strategy_id
JOIN markets m ON m.id = s.market_id
JOIN exchanges e ON e.id = m.exchange_id
WHERE o.tracking_state = 'terminal' AND s.direction::text = 'long' AND e.code::text = 'binance'
ORDER BY o.signal_id
) TO STDOUT WITH (FORMAT csv, HEADER);
COMMIT;
