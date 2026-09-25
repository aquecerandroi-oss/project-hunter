SET statement_timeout='120s';
SELECT rs.name||'/'||rs.version rs, pr.reasons->0->>'rule' gate, pr.reasons->0->>'series' series, count(*), count(DISTINCT b.mint) mints,
  sum(CASE WHEN b.pnl_sol IS NULL THEN 1 ELSE 0 END) nullpnl
FROM meme_paper_bets b JOIN meme_proposals pr ON pr.id=b.proposal_id JOIN meme_rule_sets rs ON rs.id=b.rule_set_id
WHERE b.exit_at IS NOT NULL GROUP BY 1,2,3 ORDER BY 1;
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='meme_paper_bets' ORDER BY ordinal_position;
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='meme_live_positions' ORDER BY ordinal_position;
