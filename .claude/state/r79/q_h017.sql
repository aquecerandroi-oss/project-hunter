SET statement_timeout='600s';
COPY (
  WITH arm AS (SELECT id FROM meme_rule_sets WHERE name='recuo_v1' AND version='1'),
  op5 AS (SELECT id FROM meme_rule_sets WHERE name='operator' AND version='5'),
  armed AS (
    SELECT DISTINCT ON (r.mint) r.mint, r.as_of t0, r."limit" lim
    FROM meme_gate_refusals_by_mint r WHERE r.rule_set_id=(SELECT id FROM arm) AND r.refusal='entry_pullback_armed'
    ORDER BY r.mint, r.as_of
  ),
  trail AS (
    SELECT a.mint, string_agg(r.refusal||'@'||r.as_of::text||'#'||coalesce(r.value::text,''), ' | ' ORDER BY r.as_of) outcomes
    FROM armed a JOIN meme_gate_refusals_by_mint r ON r.mint=a.mint AND r.rule_set_id=(SELECT id FROM arm)
      AND r.refusal IS DISTINCT FROM 'entry_pullback_armed' AND r.refusal IS NOT NULL AND r.as_of >= a.t0
    GROUP BY a.mint
  ),
  armp AS (
    SELECT DISTINCT ON (pr.mint, pr.features_end_time) pr.mint, pr.features_end_time, pr.id::text arm_prop, pr.status arm_prop_status,
           pr.proposed_at arm_proposed_at, (SELECT e FROM jsonb_array_elements(pr.reasons) e WHERE e->>'feature'='entry_pullback' LIMIT 1)::text pb,
           b.id::text arm_bet, b.entry_at arm_entry_at, b.exit_at arm_exit_at, b.entry->>'sol_spent' arm_size, b.pnl_sol::text arm_pnl,
           b.status arm_status, b.outcome_quality arm_oq, COALESCE(b.exit->>'reason', b.exit_intent->>'reason') arm_exit, b.high_water_x::text arm_hwx
    FROM meme_proposals pr LEFT JOIN meme_paper_bets b ON b.proposal_id=pr.id AND b.leg='single'
    WHERE pr.rule_set_id=(SELECT id FROM arm) ORDER BY pr.mint, pr.features_end_time, pr.proposed_at
  ),
  opp AS (
    SELECT DISTINCT ON (pr.mint, pr.features_end_time) pr.mint, pr.features_end_time, pr.id::text op_prop, pr.status op_prop_status,
           pr.decision->>'reason' op_decision_reason, left(pr.decision::text, 200) op_decision,
           b.id::text op_bet, b.entry_at op_entry_at, b.exit_at op_exit_at, b.entry->>'sol_spent' op_size, b.pnl_sol::text op_pnl,
           b.status op_status, b.outcome_quality op_oq, COALESCE(b.exit->>'reason', b.exit_intent->>'reason') op_exit, b.high_water_x::text op_hwx,
           lp.id::text real_id, (lp.sol_spent_lamports::numeric/1e9)::text real_size, lp.pnl_sol::text real_pnl, lp.status real_status
    FROM meme_proposals pr LEFT JOIN meme_paper_bets b ON b.proposal_id=pr.id AND b.leg='single'
    LEFT JOIN meme_live_positions lp ON lp.proposal_id=pr.id
    WHERE pr.rule_set_id=(SELECT id FROM op5) AND pr.reasons->0->>'series'='meme_event_gate_v1' AND pr.features_end_time >= '2026-09-24 00:00Z'
    ORDER BY pr.mint, pr.features_end_time, pr.proposed_at
  )
  SELECT a.mint, tk.symbol, a.t0, a.lim, tr.outcomes, ap.*, op.*
  FROM armed a
  LEFT JOIN trail tr ON tr.mint=a.mint
  LEFT JOIN armp ap ON ap.mint=a.mint AND ap.features_end_time=a.t0
  LEFT JOIN opp op ON op.mint=a.mint AND op.features_end_time=a.t0
  LEFT JOIN meme_tokens tk ON tk.mint=a.mint
  ORDER BY a.t0
) TO STDOUT WITH (FORMAT csv, HEADER);
