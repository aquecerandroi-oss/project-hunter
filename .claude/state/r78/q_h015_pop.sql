SET statement_timeout='600s';
COPY (
  WITH bets AS (
    SELECT 'real' lane, p.id::text bet_id, p.mint, rs.name||'/'||rs.version rs, pr.reasons->0->>'rule' gate,
           pr.reasons->0->>'series' series, pr.decided_at, pr.features_end_time, p.entry_at, p.exit_at,
           (p.sol_spent_lamports::numeric/1e9)::text size_sol, p.pnl_sol::text pnl_sol
    FROM meme_live_positions p JOIN meme_proposals pr ON pr.id=p.proposal_id JOIN meme_rule_sets rs ON rs.id=pr.rule_set_id
    WHERE p.status='closed'
    UNION ALL
    SELECT 'paper', b.id::text, b.mint, rs.name||'/'||rs.version, pr.reasons->0->>'rule', pr.reasons->0->>'series',
           pr.decided_at, pr.features_end_time, b.entry_at, b.exit_at, b.entry->>'sol_spent', b.pnl_sol::text
    FROM meme_paper_bets b JOIN meme_proposals pr ON pr.id=b.proposal_id JOIN meme_rule_sets rs ON rs.id=b.rule_set_id
    WHERE b.exit_at IS NOT NULL AND b.pnl_sol IS NOT NULL AND b.leg='single'
  )
  SELECT b.*, tk.symbol, tk.creator, t.as_of, (t.derived->'creation_bundle')::text AS cb
  FROM bets b JOIN meme_decision_tapes t ON t.mint=b.mint AND t.as_of=b.features_end_time
  LEFT JOIN meme_tokens tk ON tk.mint=b.mint
  WHERE b.series='meme_event_gate_v1'
  ORDER BY b.entry_at
) TO STDOUT WITH (FORMAT csv, HEADER);
