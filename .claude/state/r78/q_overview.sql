SET statement_timeout='120s';
SELECT 'live' lane, rs.name||'/'||rs.version rs, pr.reasons->0->>'rule' gate, count(*), min(p.entry_at), max(p.entry_at), sum(p.pnl_sol)
FROM meme_live_positions p JOIN meme_proposals pr ON pr.id=p.proposal_id JOIN meme_rule_sets rs ON rs.id=pr.rule_set_id
WHERE p.status='closed' GROUP BY 1,2,3 ORDER BY 2;
SELECT 'paper' lane, rs.name||'/'||rs.version rs, rs.status, b.leg, count(*), min(b.entry_at), max(b.entry_at)
FROM meme_paper_bets b JOIN meme_rule_sets rs ON rs.id=b.rule_set_id
WHERE b.exit_at IS NOT NULL GROUP BY 1,2,3,4 ORDER BY 2;
SELECT status, count(*) FROM meme_live_positions GROUP BY 1;
