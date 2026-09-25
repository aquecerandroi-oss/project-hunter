SET statement_timeout='300s';
WITH bets AS (
  SELECT 'real' lane, p.mint, rs.name||'/'||rs.version rs, pr.reasons->0->>'rule' gate, pr.reasons->0->>'series' series,
         pr.features_end_time fet, p.entry_at, (p.status='closed') resolved
  FROM meme_live_positions p JOIN meme_proposals pr ON pr.id=p.proposal_id JOIN meme_rule_sets rs ON rs.id=pr.rule_set_id
  UNION ALL
  SELECT 'paper', b.mint, rs.name||'/'||rs.version, pr.reasons->0->>'rule', pr.reasons->0->>'series', pr.features_end_time, b.entry_at,
         (b.exit_at IS NOT NULL AND b.pnl_sol IS NOT NULL)
  FROM meme_paper_bets b JOIN meme_proposals pr ON pr.id=b.proposal_id JOIN meme_rule_sets rs ON rs.id=b.rule_set_id
  WHERE b.leg='single'
)
SELECT b.lane, b.rs, b.gate, count(*) n, count(t.mint) with_tape, count(*) FILTER (WHERE resolved) res,
       count(*) FILTER (WHERE t.derived->'windows'->'10s' ? 'buy_sol' AND t.derived->'windows'->'60s' ? 'buy_sol') full_win,
       min(b.entry_at), max(b.entry_at)
FROM bets b LEFT JOIN meme_decision_tapes t ON t.mint=b.mint AND t.as_of=b.fet
WHERE b.series='meme_event_gate_v1'
GROUP BY 1,2,3 ORDER BY 1,2;
