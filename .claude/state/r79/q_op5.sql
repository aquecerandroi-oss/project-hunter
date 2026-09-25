SET statement_timeout='300s';
SELECT rs.name||'/'||rs.version rs, pr.status, pr.refusal IS NOT NULL has_ref, left(coalesce(pr.refusal,''),40) ref, count(*),
  count(b.id) paper, count(lp.id) real
FROM meme_proposals pr JOIN meme_rule_sets rs ON rs.id=pr.rule_set_id
LEFT JOIN meme_paper_bets b ON b.proposal_id=pr.id AND b.leg='single'
LEFT JOIN meme_live_positions lp ON lp.proposal_id=pr.id
WHERE rs.name IN ('operator','recuo_v1') AND pr.proposed_at >= '2026-09-24 03:45Z' AND pr.reasons->0->>'series'='meme_event_gate_v1'
GROUP BY 1,2,3,4 ORDER BY 1,5 DESC;
SELECT rs.name||'/'||rs.version rs, split_part(r.refusal,':',1) ref, count(*), count(DISTINCT r.mint) mints, min(r.as_of), max(r.as_of)
FROM meme_gate_refusals_by_mint r JOIN meme_rule_sets rs ON rs.id=r.rule_set_id
WHERE rs.name='recuo_v1' AND (r.refusal IS NULL OR r.refusal LIKE '%pullback%' OR r.refusal LIKE 'entry_%')
GROUP BY 1,2 ORDER BY 3 DESC;
