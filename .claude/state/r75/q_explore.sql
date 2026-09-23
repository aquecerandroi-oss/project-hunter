SET statement_timeout='120s';
SELECT 'live', rs.name||'/'||rs.version, pr.reasons->0->>'rule' AS gate, count(*),
       sum(CASE WHEN EXISTS (SELECT 1 FROM jsonb_array_elements(pr.reasons) e WHERE e->>'feature'='flow') THEN 1 ELSE 0 END) AS with_flow,
       sum(CASE WHEN p.exit_at IS NOT NULL THEN 1 ELSE 0 END) closed, min(pr.decided_at)::date, max(pr.decided_at)
FROM meme_live_positions p JOIN meme_proposals pr ON pr.id=p.proposal_id JOIN meme_rule_sets rs ON rs.id=pr.rule_set_id
GROUP BY 1,2,3
UNION ALL
SELECT 'paper', rs.name||'/'||rs.version, pr.reasons->0->>'rule', count(*),
       sum(CASE WHEN EXISTS (SELECT 1 FROM jsonb_array_elements(pr.reasons) e WHERE e->>'feature'='flow') THEN 1 ELSE 0 END),
       sum(CASE WHEN b.exit_at IS NOT NULL THEN 1 ELSE 0 END), min(pr.decided_at)::date, max(pr.decided_at)
FROM meme_paper_bets b JOIN meme_proposals pr ON pr.id=b.proposal_id JOIN meme_rule_sets rs ON rs.id=b.rule_set_id
WHERE b.leg='single'
GROUP BY 1,2,3 ORDER BY 1,2;
