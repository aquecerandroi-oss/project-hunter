SET statement_timeout='600s';
COPY (
  WITH src AS (
    SELECT 'live' AS lane, p.id::text AS bet_id, p.mint, tk.symbol, rs.name||'/'||rs.version AS rule_set,
           pr.id::text AS proposal_id, pr.decided_at, pr.features_end_time, pr.reasons,
           p.entry_at, p.exit_at, p.exit->>'reason' AS exit_reason,
           (p.sol_spent_lamports::numeric / 1e9)::text AS size_sol, p.pnl_sol::text AS pnl_sol
    FROM meme_live_positions p
    JOIN meme_proposals pr ON pr.id = p.proposal_id
    JOIN meme_rule_sets rs ON rs.id = pr.rule_set_id
    LEFT JOIN meme_tokens tk ON tk.mint = p.mint
    UNION ALL
    SELECT 'paper', b.id::text, b.mint, tk.symbol, rs.name||'/'||rs.version,
           pr.id::text, pr.decided_at, pr.features_end_time, pr.reasons,
           b.entry_at, b.exit_at, b.exit->>'reason', (b.entry->>'sol_spent'), b.pnl_sol::text
    FROM meme_paper_bets b
    JOIN meme_proposals pr ON pr.id = b.proposal_id
    JOIN meme_rule_sets rs ON rs.id = b.rule_set_id
    LEFT JOIN meme_tokens tk ON tk.mint = b.mint
    WHERE b.exit_at IS NOT NULL AND b.pnl_sol IS NOT NULL AND b.leg = 'single'
  )
  SELECT s.lane, s.bet_id, s.mint, s.symbol, s.rule_set, s.proposal_id,
         s.reasons->0->>'rule' AS gate, s.reasons->0->>'series' AS series,
         s.decided_at, s.features_end_time, s.entry_at, s.exit_at, s.exit_reason, s.size_sol, s.pnl_sol,
         (SELECT e::text FROM jsonb_array_elements(s.reasons) e WHERE e->>'feature'='flow' LIMIT 1) AS flow_json,
         (SELECT e->>'value' FROM jsonb_array_elements(s.reasons) e WHERE e->>'feature'='curve_progress_pct' LIMIT 1) AS progress_pct
  FROM src s
  WHERE s.reasons->0->>'rule' LIKE 'fluxo_e_holders/%'
     OR s.lane = 'live'
  ORDER BY s.decided_at
) TO STDOUT WITH (FORMAT csv, HEADER);
