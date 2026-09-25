SET statement_timeout='120s';
SELECT column_name FROM information_schema.columns WHERE table_name='meme_proposals' ORDER BY ordinal_position;
SELECT pr.id, rs.name||'/'||rs.version rs, pr.proposed_at, pr.features_end_time, pr.decided_at, pr.status
FROM meme_proposals pr JOIN meme_rule_sets rs ON rs.id=pr.rule_set_id
WHERE pr.mint IN (SELECT mint FROM meme_live_positions p JOIN meme_tokens t USING (mint) WHERE t.symbol IN ('BAGI','007'))
  AND rs.name='operator' ORDER BY pr.proposed_at;
SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'meme%refus%' OR table_name LIKE 'meme_orders%' OR table_name LIKE 'meme_risk%';
