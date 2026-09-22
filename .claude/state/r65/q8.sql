SET statement_timeout='60s';
SELECT id, name, version, status, created_at FROM meme_rule_sets ORDER BY name, version;
\echo == positions by ruleset version ==
SELECT rs.name||'/'||rs.version AS rsv, count(*), sum(p.pnl_sol),
  count(*) FILTER (WHERE p.exit_intent->>'reason'='target') AS targets
FROM meme_live_positions p JOIN meme_proposals pr ON pr.id=p.proposal_id JOIN meme_rule_sets rs ON rs.id=pr.rule_set_id
WHERE p.status='closed' GROUP BY 1 ORDER BY 1;
