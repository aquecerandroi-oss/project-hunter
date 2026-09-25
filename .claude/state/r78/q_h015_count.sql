SET statement_timeout='300s';
SELECT min(as_of), max(as_of), count(*) tapes, count(*) FILTER (WHERE derived ? 'creation_bundle') with_cb,
  min(as_of) FILTER (WHERE derived ? 'creation_bundle') first_cb
FROM meme_decision_tapes;
WITH bets AS (
  SELECT 'real' lane, p.mint, p.pnl_sol, pr.features_end_time, pr.reasons->0->>'series' series, rs.name||'/'||rs.version rs, p.entry_at
  FROM meme_live_positions p JOIN meme_proposals pr ON pr.id=p.proposal_id JOIN meme_rule_sets rs ON rs.id=pr.rule_set_id WHERE p.status='closed'
  UNION ALL
  SELECT 'paper', b.mint, b.pnl_sol, pr.features_end_time, pr.reasons->0->>'series', rs.name||'/'||rs.version, b.entry_at
  FROM meme_paper_bets b JOIN meme_proposals pr ON pr.id=b.proposal_id JOIN meme_rule_sets rs ON rs.id=b.rule_set_id
  WHERE b.exit_at IS NOT NULL AND b.pnl_sol IS NOT NULL AND b.leg='single'
)
SELECT b.lane, (t.derived->'creation_bundle'->>'create_signature') IS NOT NULL has_sig,
  count(*) bets, count(DISTINCT b.mint) mints, min(b.entry_at), max(b.entry_at),
  count(DISTINCT b.mint) FILTER (WHERE b.rs IN ('operator/5','operator/6') OR b.rs LIKE 'flow_v2/%' OR b.rs LIKE 'recuo_v1/%') desk_mints
FROM bets b JOIN meme_decision_tapes t ON t.mint=b.mint AND t.as_of=b.features_end_time
WHERE t.derived ? 'creation_bundle'
GROUP BY 1,2 ORDER BY 1,2;
