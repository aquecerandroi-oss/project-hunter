SET statement_timeout='60s';
SELECT column_name FROM information_schema.columns WHERE table_name='meme_rule_sets' ORDER BY ordinal_position;
SELECT rs.id, rs.name, rs.version, rs.created_at, count(p.id) FROM meme_rule_sets rs JOIN meme_proposals pr ON pr.rule_set_id=rs.id JOIN meme_live_positions p ON p.proposal_id=pr.id WHERE p.entry_at >= '2026-09-19 03:00:00+00' GROUP BY 1,2,3,4 ORDER BY 4;
