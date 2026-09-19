SET statement_timeout='60s';
SELECT o.proposal_id, t.symbol, o.side, o.attempt, o.status, o.reason, o.received_at, o.admitted_at, o.simulated_at, o.signing_at, o.submitted_at, o.settled_at,
  o.intent->>'exit_reason' AS exit_reason, o.intent->>'min_sol_output' AS min_sol_output, o.intent->>'max_sol_cost' AS max_sol_cost, o.intent->>'token_amount' AS tok, o.intent->>'sol_final' AS sol_final, o.intent->'priority_fee' AS pf, o.fill->>'sol_amount' AS fill_sol, o.fill->>'sell_net_lamports' AS sell_net, o.fill->>'block_time' AS fill_bt, o.fill->>'slot' AS fill_slot, o.tx_signature
FROM meme_live_orders o JOIN meme_proposals p ON p.id=o.proposal_id JOIN meme_tokens t ON t.mint=p.mint
WHERE o.received_at >= '2026-09-19 03:00:00+00'
ORDER BY o.received_at;
