SET statement_timeout='300s';
COPY (
  SELECT 'real' AS lane, p.id::text AS bet_id, p.mint, tk.symbol, rs.name||'/'||rs.version AS rule_set,
         pr.reasons->0->>'rule' AS gate, pr.reasons->0->>'series' AS series,
         pr.decided_at, pr.features_end_time, p.entry_at, p.exit_at, COALESCE(p.exit->>'reason', p.exit_intent->>'reason') AS exit_reason,
         (p.sol_spent_lamports::numeric/1e9)::text AS size_sol, p.pnl_sol::text AS pnl_sol
  FROM meme_live_positions p
  JOIN meme_proposals pr ON pr.id = p.proposal_id
  JOIN meme_rule_sets rs ON rs.id = pr.rule_set_id
  LEFT JOIN meme_tokens tk ON tk.mint = p.mint
  WHERE p.status='closed'
  UNION ALL
  SELECT 'paper', b.id::text, b.mint, tk.symbol, rs.name||'/'||rs.version,
         pr.reasons->0->>'rule', pr.reasons->0->>'series',
         pr.decided_at, pr.features_end_time, b.entry_at, b.exit_at, COALESCE(b.exit->>'reason', b.exit_intent->>'reason'),
         (b.entry->>'sol_spent'), b.pnl_sol::text
  FROM meme_paper_bets b
  JOIN meme_proposals pr ON pr.id = b.proposal_id
  JOIN meme_rule_sets rs ON rs.id = b.rule_set_id
  LEFT JOIN meme_tokens tk ON tk.mint = b.mint
  WHERE b.exit_at IS NOT NULL AND b.pnl_sol IS NOT NULL AND b.leg = 'single'
    AND (rs.name IN ('operator','flow_v2','recuo_v1') OR pr.reasons->0->>'rule' LIKE 'fluxo\_e\_holders/%')
  ORDER BY 10
) TO STDOUT WITH (FORMAT csv, HEADER);
