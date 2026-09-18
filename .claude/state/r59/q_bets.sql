SET statement_timeout='60s';
SELECT 'paper' AS kind, rs.name||'/'||rs.version AS rs, b.id, b.mint, b.entry_at, b.exit_at,
  b.entry->'snapshot'->>'mcap_sol' AS entry_mcap, b.entry->>'average_price_sol' AS entry_price,
  b.initial_risk_sol AS stake, b.pnl_sol, b.r_multiple, b.exit->>'reason' AS exit_reason,
  b.exit->'snapshot'->>'mcap_sol' AS exit_mcap, b.creator_sold_seen_at, b.high_water_x, b.outcome_quality, b.entry->'snapshot'->>'observed_at' AS entry_snapshot_at
FROM meme_paper_bets b JOIN meme_rule_sets rs ON rs.id=b.rule_set_id
WHERE b.entry_at >= '2026-09-16 15:00+00' AND (rs.name,rs.version) IN (('operator','5'),('flow_v2','5'),('flow_v2','2'),('flow_v2','6'),('flow_v2','8'))
UNION ALL
SELECT 'live', 'operator/5 real', p.id, p.mint, p.entry_at, p.exit_at,
  ((p.entry->>'virtual_sol_reserves_after')::numeric / (p.entry->>'virtual_token_reserves_after')::numeric * 1e9 / 1e9 * 1e6)::text,
  ((p.entry->>'virtual_sol_reserves_after')::numeric / 1e9 / ((p.entry->>'virtual_token_reserves_after')::numeric/1e6))::text,
  p.initial_risk_sol, p.pnl_sol, p.r_multiple, p.exit->>'reason',
  ((p.exit->>'virtual_sol_reserves_after')::numeric / (p.exit->>'virtual_token_reserves_after')::numeric * 1e6)::text,
  p.creator_sold_seen_at, p.high_water_sol / p.initial_risk_sol, 'live', p.entry->>'block_time'
FROM meme_live_positions p
ORDER BY 5;
