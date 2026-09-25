SET statement_timeout='600s';
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
  SELECT b.*, tk.symbol, t.as_of tape_as_of, t.recorded_at, t.trades_in_window, t.derived->>'reason' tape_reason,
         t.derived->>'as_of' derived_as_of, (t.derived->'coverage'->>'gaps') gaps, (t.derived->'windows')::text win,
         (SELECT max((x->>'received_at')::timestamptz) FROM jsonb_array_elements(t.trades) x) max_recv,
         (SELECT max((x->>'block_time')::timestamptz) FROM jsonb_array_elements(t.trades) x) max_bt
  FROM bets b LEFT JOIN meme_decision_tapes t ON t.mint=b.mint AND t.as_of=b.features_end_time
  LEFT JOIN meme_tokens tk ON tk.mint=b.mint
  WHERE b.series='meme_event_gate_v1' AND b.gate LIKE 'fluxo\_e\_holders/%' AND b.features_end_time >= '2026-09-24 00:00Z'
  ORDER BY b.features_end_time
) TO STDOUT WITH (FORMAT csv, HEADER);
