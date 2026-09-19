SET statement_timeout='60s';
\x
SELECT p.id, p.proposal_id, p.mint, t.symbol, t.name, p.status, p.entry_at, p.exit_at, p.tokens, p.sol_spent_lamports, p.sol_received_lamports, p.pnl_sol, p.r_multiple, p.high_water_sol, p.mark_sol, p.mark_at, p.mark_source, p.params, p.exit_intent, p.exit, p.entry, p.creator_sold_seen_at, p.creator_sold_fraction, p.sell_requested_at, p.migrated
FROM meme_live_positions p LEFT JOIN meme_tokens t USING (mint)
WHERE p.entry_at >= '2026-09-19 03:00:00+00'
ORDER BY p.entry_at;
