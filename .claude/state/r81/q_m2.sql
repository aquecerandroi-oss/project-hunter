SELECT rs.name||'/'||rs.version rs, rs.status, count(DISTINCT pr.id) props, count(DISTINCT b.id) bets, min(pr.decided_at), max(pr.decided_at)
FROM meme_rule_sets rs LEFT JOIN meme_proposals pr ON pr.rule_set_id=rs.id LEFT JOIN meme_paper_bets b ON b.proposal_id=pr.id
WHERE rs.params::text LIKE '%require_higher_lows": true%' OR rs.params::text LIKE '%max_distance_to_support_pct": "%' OR rs.name LIKE 'trendline%'
GROUP BY 1,2;
