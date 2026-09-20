SET statement_timeout='60s';
COPY (
SELECT p.id AS position_id, t.symbol, p.mint, rs.name AS rule_set, rs.id AS rule_set_id, pr.origin, pr.mode, p.entry_at, p.exit_at, p.sol_spent_lamports, p.sol_received_lamports, p.pnl_sol, p.high_water_sol, p.exit_intent->>'reason' AS exit_reason, p.exit_intent->>'decided_at' AS decided_at,
 (p.entry->>'slot')::bigint AS entry_slot, p.entry->>'block_time' AS entry_bt, (p.entry->>'token_amount')::numeric AS tokens_entry, (p.entry->>'virtual_sol_reserves_after')::numeric AS vsol_after, (p.entry->>'virtual_token_reserves_after')::numeric AS vtok_after,
 (p.exit->>'slot')::bigint AS exit_slot, p.exit->>'block_time' AS exit_bt, (p.exit->>'sol_amount')::numeric AS exit_sol, (p.exit->>'sell_net_lamports')::numeric AS exit_net, (p.exit->>'virtual_sol_reserves_after')::numeric AS exit_vsol_after, (p.exit->>'virtual_token_reserves_after')::numeric AS exit_vtok_after,
 t.creator, t.created_at, t.completed_at
FROM meme_live_positions p LEFT JOIN meme_tokens t USING (mint) LEFT JOIN meme_proposals pr ON pr.id=p.proposal_id LEFT JOIN meme_rule_sets rs ON rs.id=pr.rule_set_id
WHERE p.entry_at >= '2026-09-19 03:00:00+00'
ORDER BY p.entry_at
) TO STDOUT WITH CSV HEADER;
