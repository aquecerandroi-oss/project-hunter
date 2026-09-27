SET statement_timeout='300s';
SELECT rs.name||'/'||rs.version rs, count(*) n, min(r.as_of), max(r.as_of),
  count(*) FILTER (WHERE refusal='entry_pullback_armed') armed
FROM meme_gate_refusals_by_mint r JOIN meme_rule_sets rs ON rs.id=r.rule_set_id
WHERE r.rule_set_id IN ('01994d00-6c1a-7000-8000-00000000001d','01994d00-6c1a-7000-8000-00000000001e')
GROUP BY 1;
SELECT refusal_base, count(*) FROM (SELECT split_part(coalesce(refusal,'<null>'),':',1) refusal_base FROM meme_gate_refusals_by_mint
 WHERE rule_set_id='01994d00-6c1a-7000-8000-00000000001d' AND as_of>='2026-09-26 15:05:30Z') x GROUP BY 1 ORDER BY 2 DESC LIMIT 30;
