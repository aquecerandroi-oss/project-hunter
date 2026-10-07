BEGIN READ ONLY;
SELECT rs.name||'/'||rs.version rs, (SELECT string_agg(k, ',' ORDER BY k) FROM jsonb_object_keys(b.params) k) keys, b.params->>'exit_on_creator_dump' e1, rs.params->>'exit_on_creator_dump' e2
FROM meme_paper_bets b JOIN meme_rule_sets rs ON rs.id=b.rule_set_id
WHERE rs.name||'/'||rs.version IN ('absorb_v0/1','absorb_v0/2','flow_v2/1','recuo_v1/1','recuo_ctrl_v1/1','flow_v2/6','flow_v2/7','flow_v2/8','flow_v2/9','operator/5','operator/6')
AND b.id IN (SELECT DISTINCT ON (rule_set_id) id FROM meme_paper_bets ORDER BY rule_set_id, entry_at DESC);
COMMIT;
