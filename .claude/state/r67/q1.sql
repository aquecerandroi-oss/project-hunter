SET statement_timeout='180s';
COPY (
WITH f AS (
  SELECT b.id AS bet_id, b.proposal_id, b.mint,
         rs.name||'/'||rs.version AS arm,
         b.entry_at, b.exit_at, b.status, b.outcome_quality,
         b.pnl_sol, b.high_water_x,
         b.exit_intent->>'reason' AS exit_reason,
         b.params->>'size_sol' AS size_sol,
         b.params->>'target_x' AS target_x,
         b.params->>'max_hold_s' AS max_hold_s,
         b.params->>'trailing_pct' AS trailing_pct,
         b.entry->'snapshot'->>'real_sol_reserves' AS real_sol,
         b.entry->'snapshot'->>'mcap_sol' AS mcap_sol,
         (SELECT e FROM jsonb_array_elements(pr.reasons) e WHERE e->>'feature'='flow' LIMIT 1) AS flow,
         (SELECT e->>'value' FROM jsonb_array_elements(pr.reasons) e WHERE e->>'feature'='age_s' LIMIT 1) AS age_s,
         (SELECT e->>'value' FROM jsonb_array_elements(pr.reasons) e WHERE e->>'feature'='curve_progress_pct' LIMIT 1) AS progress_pct,
         (SELECT e->>'value' FROM jsonb_array_elements(pr.reasons) e WHERE e->>'feature'='creator_net_seller' LIMIT 1) AS creator_net_seller,
         EXISTS (SELECT 1 FROM meme_live_positions lp WHERE lp.proposal_id=b.proposal_id) AS shared_live
  FROM meme_paper_bets b
  JOIN meme_rule_sets rs ON rs.id=b.rule_set_id
  JOIN meme_proposals pr ON pr.id=b.proposal_id
  WHERE b.entry_at >= '2026-09-11'
)
SELECT bet_id, proposal_id, mint, arm,
       entry_at, exit_at, status, outcome_quality, exit_reason,
       pnl_sol, high_water_x, size_sol, target_x, max_hold_s, trailing_pct,
       real_sol, mcap_sol, age_s, progress_pct, creator_net_seller, shared_live,
       flow->>'buys_1m' AS buys_1m, flow->>'sells_1m' AS sells_1m,
       flow->>'unique_buyers_1m' AS unique_buyers_1m, flow->>'snipers' AS snipers,
       flow->>'dev_share' AS dev_share, flow->>'net_sol_flow_1m' AS net_sol_flow_1m,
       flow->>'mcap_delta_60s' AS mcap_delta_60s
FROM f ORDER BY entry_at
) TO STDOUT WITH CSV HEADER;
