SET statement_timeout='600s';
COPY (
  SELECT 'real' AS pop, p.id::text AS bet_id, p.mint, tk.symbol,
         rs.name||'/'||rs.version AS rule_set, pr.reasons->0->>'rule' AS gate, pr.reasons->0->>'series' AS series,
         pr.proposed_at, pr.features_end_time, pr.decided_at,
         pr.quote::text AS quote_json,
         p.entry_at, p.exit_at, p.exit_intent->>'reason' AS exit_reason,
         p.sol_spent_lamports::text AS spent_lamports, p.sol_received_lamports::text AS received_lamports,
         p.high_water_sol::text AS high_water_sol,
         p.pnl_sol::text AS pnl_sol, p.params::text AS params, p.entry::text AS entry_json
  FROM meme_live_positions p
  JOIN meme_proposals pr ON pr.id = p.proposal_id
  JOIN meme_rule_sets rs ON rs.id = pr.rule_set_id
  LEFT JOIN meme_tokens tk ON tk.mint = p.mint
  WHERE p.status='closed'
  UNION ALL
  SELECT 'paper', b.id::text, b.mint, tk.symbol,
         rs.name||'/'||rs.version, pr.reasons->0->>'rule', pr.reasons->0->>'series',
         pr.proposed_at, pr.features_end_time, pr.decided_at,
         pr.quote::text,
         b.entry_at, b.exit_at, COALESCE(b.exit_intent->>'reason', b.exit->>'reason'),
         NULL, NULL, b.high_water_x::text, b.pnl_sol::text, b.params::text, b.entry::text
  FROM meme_paper_bets b
  JOIN meme_proposals pr ON pr.id = b.proposal_id
  JOIN meme_rule_sets rs ON rs.id = b.rule_set_id
  LEFT JOIN meme_tokens tk ON tk.mint = b.mint
  WHERE b.exit_at IS NOT NULL AND b.pnl_sol IS NOT NULL AND b.leg = 'single'
    AND pr.reasons->0->>'rule' LIKE 'fluxo\_e\_holders/%'
    AND pr.proposed_at < now() - interval '10 minutes'
  ORDER BY 8
) TO STDOUT WITH (FORMAT csv, HEADER);
