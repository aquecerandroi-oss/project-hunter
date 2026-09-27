-- R82 — H-017 (EXP-M25): armações de recuo_v1/1 desde o início da coorte (2026-09-26 15:05:30Z), 1.ª por mint,
-- com a aposta do braço, o desfecho na trilha, o par de recuo_ctrl_v1/1 em (mint, t0) e a sombra do operator/5 (descritivo).
SET statement_timeout='600s';
COPY (
  WITH arm AS (SELECT '01994d00-6c1a-7000-8000-00000000001d'::uuid id),
  ctl AS (SELECT '01994d00-6c1a-7000-8000-00000000001e'::uuid id),
  op5 AS (SELECT '01994d00-6c1a-7000-8000-000000000011'::uuid id),
  firstarm AS (
    SELECT DISTINCT ON (r.mint) r.mint, r.as_of first_t0_any
    FROM meme_gate_refusals_by_mint r WHERE r.rule_set_id=(SELECT id FROM arm) AND r.refusal='entry_pullback_armed'
    ORDER BY r.mint, r.as_of
  ),
  armed AS (
    SELECT DISTINCT ON (r.mint) r.mint, r.as_of t0, r."limit" lim,
           (SELECT count(*) FROM meme_gate_refusals_by_mint r2 WHERE r2.rule_set_id=(SELECT id FROM arm) AND r2.mint=r.mint
              AND r2.refusal='entry_pullback_armed') n_armed
    FROM meme_gate_refusals_by_mint r WHERE r.rule_set_id=(SELECT id FROM arm) AND r.refusal='entry_pullback_armed'
      AND r.as_of >= '2026-09-26 15:05:30Z'
    ORDER BY r.mint, r.as_of
  ),
  trail AS (
    SELECT a.mint, string_agg(r.refusal||'@'||r.as_of::text||'#'||coalesce(r.value::text,''), ' | ' ORDER BY r.as_of) outcomes
    FROM armed a JOIN meme_gate_refusals_by_mint r ON r.mint=a.mint AND r.rule_set_id=(SELECT id FROM arm)
      AND r.refusal IS NOT NULL AND r.as_of >= a.t0
      AND (r.refusal LIKE 'pullback_%' OR r.refusal='no_pullback')
    GROUP BY a.mint
  ),
  armp AS (
    SELECT DISTINCT ON (pr.mint, pr.features_end_time) pr.mint, pr.features_end_time, pr.id::text arm_prop, pr.status arm_prop_status,
           pr.decided_by arm_decided_by, pr.proposed_at arm_proposed_at,
           (SELECT e FROM jsonb_array_elements(pr.reasons) e WHERE e->>'feature'='entry_pullback' LIMIT 1)::text pb,
           b.id::text arm_bet, b.entry_at arm_entry_at, b.exit_at arm_exit_at, b.entry->>'sol_spent' arm_size, b.pnl_sol::text arm_pnl,
           b.status arm_status, b.outcome_quality arm_oq, COALESCE(b.exit->>'reason', b.exit_intent->>'reason') arm_exit, b.high_water_x::text arm_hwx,
           b.entry->>'decided_at' arm_decided_at, b.entry->'snapshot'->>'observed_at' arm_snap_at,
           b.entry->'snapshot'->>'virtual_sol_reserves' arm_vsol, b.entry->'snapshot'->>'virtual_token_reserves' arm_vtok,
           b.entry->>'average_price_sol' arm_avg_px, b.entry->>'marginal_price_before_sol' arm_mpx_before,
           b.entry->>'decision_to_fill_s' arm_d2f_s, b.entry->>'fill_delay_snapshots' arm_fill_delay
    FROM meme_proposals pr LEFT JOIN meme_paper_bets b ON b.proposal_id=pr.id AND b.leg='single'
    WHERE pr.rule_set_id=(SELECT id FROM arm) AND pr.features_end_time >= '2026-09-26 15:00Z'
    ORDER BY pr.mint, pr.features_end_time, pr.proposed_at
  ),
  ctlp AS (
    SELECT DISTINCT ON (pr.mint, pr.features_end_time) pr.mint, pr.features_end_time, pr.id::text ctl_prop, pr.status ctl_prop_status,
           pr.decided_by ctl_decided_by, pr.proposed_at ctl_proposed_at, pr.reasons->0->>'series' ctl_series,
           b.id::text ctl_bet, b.entry_at ctl_entry_at, b.exit_at ctl_exit_at, b.entry->>'sol_spent' ctl_size, b.pnl_sol::text ctl_pnl,
           b.status ctl_status, b.outcome_quality ctl_oq, COALESCE(b.exit->>'reason', b.exit_intent->>'reason') ctl_exit, b.high_water_x::text ctl_hwx,
           b.entry->>'decided_at' ctl_decided_at, b.entry->'snapshot'->>'observed_at' ctl_snap_at,
           b.entry->'snapshot'->>'virtual_sol_reserves' ctl_vsol, b.entry->'snapshot'->>'virtual_token_reserves' ctl_vtok,
           b.entry->>'average_price_sol' ctl_avg_px, b.entry->>'marginal_price_before_sol' ctl_mpx_before,
           b.entry->>'decision_to_fill_s' ctl_d2f_s, b.entry->>'fill_delay_snapshots' ctl_fill_delay,
           (SELECT count(*) FROM meme_live_positions lp WHERE lp.proposal_id=pr.id) ctl_live_n
    FROM meme_proposals pr LEFT JOIN meme_paper_bets b ON b.proposal_id=pr.id AND b.leg='single'
    WHERE pr.rule_set_id=(SELECT id FROM ctl)
    ORDER BY pr.mint, pr.features_end_time, pr.proposed_at
  ),
  ctlfirst AS (
    SELECT DISTINCT ON (pr.mint) pr.mint, pr.features_end_time ctl_first_fet, pr.reasons->0->>'series' ctl_first_series, pr.status ctl_first_status
    FROM meme_proposals pr WHERE pr.rule_set_id=(SELECT id FROM ctl) ORDER BY pr.mint, pr.features_end_time, pr.proposed_at
  ),
  ctlref AS (
    SELECT a.mint, string_agg(r.refusal, ',' ORDER BY r.refusal) ctl_refusals_t0
    FROM armed a JOIN meme_gate_refusals_by_mint r ON r.mint=a.mint AND r.rule_set_id=(SELECT id FROM ctl) AND r.as_of=a.t0
    GROUP BY a.mint
  ),
  opp AS (
    SELECT DISTINCT ON (pr.mint, pr.features_end_time) pr.mint, pr.features_end_time, pr.status op_prop_status,
           b.entry->>'sol_spent' op_size, b.pnl_sol::text op_pnl, b.status op_status, b.outcome_quality op_oq,
           b.entry->'snapshot'->>'observed_at' op_snap_at
    FROM meme_proposals pr LEFT JOIN meme_paper_bets b ON b.proposal_id=pr.id AND b.leg='single'
    WHERE pr.rule_set_id=(SELECT id FROM op5) AND pr.features_end_time >= '2026-09-26 15:00Z'
    ORDER BY pr.mint, pr.features_end_time, pr.proposed_at
  )
  SELECT now() extracted_at, a.mint, tk.symbol, a.t0, a.lim, a.n_armed, fa.first_t0_any, tr.outcomes,
         ap.arm_prop, ap.arm_prop_status, ap.arm_decided_by, ap.arm_proposed_at, ap.pb, ap.arm_bet, ap.arm_entry_at, ap.arm_exit_at,
         ap.arm_size, ap.arm_pnl, ap.arm_status, ap.arm_oq, ap.arm_exit, ap.arm_hwx, ap.arm_decided_at, ap.arm_snap_at, ap.arm_vsol,
         ap.arm_vtok, ap.arm_avg_px, ap.arm_mpx_before, ap.arm_d2f_s, ap.arm_fill_delay,
         cp.ctl_prop, cp.ctl_prop_status, cp.ctl_decided_by, cp.ctl_proposed_at, cp.ctl_series, cp.ctl_bet, cp.ctl_entry_at, cp.ctl_exit_at,
         cp.ctl_size, cp.ctl_pnl, cp.ctl_status, cp.ctl_oq, cp.ctl_exit, cp.ctl_hwx, cp.ctl_decided_at, cp.ctl_snap_at, cp.ctl_vsol,
         cp.ctl_vtok, cp.ctl_avg_px, cp.ctl_mpx_before, cp.ctl_d2f_s, cp.ctl_fill_delay, cp.ctl_live_n,
         cf.ctl_first_fet, cf.ctl_first_series, cf.ctl_first_status, cr.ctl_refusals_t0,
         op.op_prop_status, op.op_size, op.op_pnl, op.op_status, op.op_oq, op.op_snap_at
  FROM armed a
  JOIN firstarm fa ON fa.mint=a.mint
  LEFT JOIN trail tr ON tr.mint=a.mint
  LEFT JOIN armp ap ON ap.mint=a.mint AND ap.features_end_time=a.t0
  LEFT JOIN ctlp cp ON cp.mint=a.mint AND cp.features_end_time=a.t0
  LEFT JOIN ctlfirst cf ON cf.mint=a.mint
  LEFT JOIN ctlref cr ON cr.mint=a.mint
  LEFT JOIN opp op ON op.mint=a.mint AND op.features_end_time=a.t0
  LEFT JOIN meme_tokens tk ON tk.mint=a.mint
  ORDER BY a.t0
) TO STDOUT WITH (FORMAT csv, HEADER);
