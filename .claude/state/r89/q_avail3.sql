SET statement_timeout='300s';
BEGIN READ ONLY;
-- 6. por conjunto e pista: propostas em Mayhem vs total (sem desfechos)
SELECT rs.name||'/'||rs.version rs, p.reasons->0->>'series' series,
       count(*) FILTER (WHERE t.mayhem_enabled) may, count(*) tot,
       count(DISTINCT p.mint) FILTER (WHERE t.mayhem_enabled) may_mints,
       min(p.decided_at) FILTER (WHERE t.mayhem_enabled) a, max(p.decided_at) FILTER (WHERE t.mayhem_enabled) z,
       bool_or(rs.params ? 'exclude_mayhem') declares, max(rs.params->>'exclude_mayhem') excl
FROM meme_proposals p JOIN meme_rule_sets rs ON rs.id=p.rule_set_id LEFT JOIN meme_tokens t ON t.mint=p.mint
GROUP BY 1,2 HAVING count(*) FILTER (WHERE t.mayhem_enabled) > 0 ORDER BY 3 DESC;
COMMIT;
