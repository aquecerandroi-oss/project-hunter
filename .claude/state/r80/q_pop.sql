SET statement_timeout='900s';
COPY (
  WITH bets AS (
    SELECT 'real' lane, p.id::text bet_id, p.mint, rs.name||'/'||rs.version rs, pr.reasons->0->>'rule' gate,
           pr.reasons->0->>'series' series, pr.id::text proposal_id, pr.decided_at, pr.features_end_time, p.entry_at, p.exit_at,
           COALESCE(p.exit->>'reason', p.exit_intent->>'reason') exit_reason, p.status,
           (p.sol_spent_lamports::numeric/1e9)::text size_sol, p.pnl_sol::text pnl_sol,
           p.high_water_sol::text hw_sol, p.initial_risk_sol::text cost_sol, NULL::text hw_x, NULL::text oq
    FROM meme_live_positions p JOIN meme_proposals pr ON pr.id=p.proposal_id JOIN meme_rule_sets rs ON rs.id=pr.rule_set_id
    UNION ALL
    SELECT 'paper', b.id::text, b.mint, rs.name||'/'||rs.version, pr.reasons->0->>'rule', pr.reasons->0->>'series', pr.id::text,
           pr.decided_at, pr.features_end_time, b.entry_at, b.exit_at, COALESCE(b.exit->>'reason', b.exit_intent->>'reason'), b.status,
           b.entry->>'sol_spent', b.pnl_sol::text, NULL, b.initial_risk_sol::text, b.high_water_x::text, b.outcome_quality
    FROM meme_paper_bets b JOIN meme_proposals pr ON pr.id=b.proposal_id JOIN meme_rule_sets rs ON rs.id=b.rule_set_id
    WHERE b.leg='single'
  )
  SELECT b.*, tk.symbol, tk.created_at tok_created_at,
    (SELECT max(n) FROM (SELECT slot, count(DISTINCT trader) n FROM meme_trades mt
        WHERE mt.mint=b.mint AND mt.side='sell' AND mt.block_time >= b.entry_at
          AND mt.block_time <= LEAST(b.exit_at, b.entry_at + interval '300 seconds') GROUP BY slot) s) sellers_slot,
    (SELECT count(*) FROM meme_trades mt WHERE mt.mint=b.mint AND mt.block_time >= b.entry_at
          AND mt.block_time <= LEAST(b.exit_at, b.entry_at + interval '300 seconds')) trades_in_hold
  FROM bets b LEFT JOIN meme_tokens tk ON tk.mint=b.mint
  WHERE b.gate LIKE 'fluxo\_e\_holders/%'
  ORDER BY b.decided_at
) TO STDOUT WITH (FORMAT csv, HEADER);
