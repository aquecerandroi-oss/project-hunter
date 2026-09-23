SET statement_timeout='120s';
COPY (
SELECT p.id AS position_id, p.proposal_id, p.mint, t.symbol, t.creator, t.created_at AS token_created_at,
  rs.name AS rule_set, rs.version AS rule_set_version, pr.origin, pr.mode,
  p.entry_at, p.exit_at, p.sol_spent_lamports, p.sol_received_lamports, p.pnl_sol, p.r_multiple,
  p.high_water_sol, p.initial_risk_sol,
  p.exit_intent->>'reason' AS exit_reason, p.exit_intent->>'decided_at' AS exit_decided_at,
  p.params::text AS params, pr.decision::text AS decision, pr.reasons::text AS reasons,
  pr.quote::text AS quote, pr.proposed_at, pr.decided_at,
  p.entry::text AS entry_json, p.exit::text AS exit_json,
  p.creator_sold_seen_at, p.creator_sold_fraction
FROM meme_live_positions p
LEFT JOIN meme_tokens t USING (mint)
LEFT JOIN meme_proposals pr ON pr.id=p.proposal_id
LEFT JOIN meme_rule_sets rs ON rs.id=pr.rule_set_id
WHERE p.status='closed'
ORDER BY p.entry_at
) TO STDOUT WITH CSV HEADER;
