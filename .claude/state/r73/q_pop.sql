SET statement_timeout='600s';
COPY (
  SELECT 'live' AS lane, p.id::text AS bet_id, p.mint, tk.symbol, tk.creator,
         rs.name||'/'||rs.version AS rule_set, rs.kind AS rs_kind,
         pr.decided_at, pr.features_end_time,
         pr.quote->>'observed_at'   AS quote_observed_at,
         pr.quote->>'real_sol_reserves' AS quote_real_sol,
         pr.quote->>'source'        AS quote_source,
         tk.created_at              AS token_created_at,
         tk.initial_virtual_sol_reserves AS init_vsol,
         p.entry_at, p.exit_at, p.exit->>'reason' AS exit_reason,
         (p.sol_spent_lamports::numeric / 1e9)::text AS size_sol,
         p.pnl_sol::text AS pnl_sol, p.r_multiple::text AS r_multiple,
         (p.entry->>'virtual_sol_reserves_after') AS entry_vsol_after,
         (p.entry->>'sol_amount') AS entry_sol_amount,
         (p.entry->>'block_time') AS entry_block_time
  FROM meme_live_positions p
  JOIN meme_proposals pr ON pr.id = p.proposal_id
  JOIN meme_rule_sets rs ON rs.id = pr.rule_set_id
  LEFT JOIN meme_tokens tk ON tk.mint = p.mint
  UNION ALL
  SELECT 'paper', b.id::text, b.mint, tk.symbol, tk.creator,
         rs.name||'/'||rs.version, rs.kind,
         pr.decided_at, pr.features_end_time,
         pr.quote->>'observed_at', pr.quote->>'real_sol_reserves', pr.quote->>'source',
         tk.created_at, tk.initial_virtual_sol_reserves,
         b.entry_at, b.exit_at, b.exit->>'reason',
         (b.entry->>'sol_spent'), b.pnl_sol::text, b.r_multiple::text,
         NULL, NULL, NULL
  FROM meme_paper_bets b
  JOIN meme_proposals pr ON pr.id = b.proposal_id
  JOIN meme_rule_sets rs ON rs.id = b.rule_set_id
  LEFT JOIN meme_tokens tk ON tk.mint = b.mint
  WHERE b.exit_at IS NOT NULL AND b.pnl_sol IS NOT NULL AND b.leg = 'single'
  ORDER BY 8
) TO STDOUT WITH (FORMAT csv, HEADER);
