SET statement_timeout='60s';
COPY (
SELECT p.id, p.proposal_id, p.mint, t.symbol, t.creator, p.status, p.entry_at, p.exit_at, p.tokens, p.sol_spent_lamports, p.sol_received_lamports, p.pnl_sol, p.r_multiple, p.high_water_sol, p.mark_sol, p.mark_at, p.params::text AS params, p.exit_intent::text AS exit_intent, p.exit::text AS exit_json, p.entry::text AS entry_json
FROM meme_live_positions p LEFT JOIN meme_tokens t USING (mint)
WHERE p.entry_at >= '2026-09-19 03:00:00+00'
ORDER BY p.entry_at
) TO STDOUT WITH CSV HEADER;
