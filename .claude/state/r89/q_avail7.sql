SET statement_timeout='120s';
BEGIN READ ONLY;
-- 12. covariáveis da decisão, sem desfecho: frequência de cada recusa por grupo Mayhem
WITH pb AS (SELECT p.reasons->0 blk FROM meme_paper_bets b JOIN meme_proposals p ON p.id=b.proposal_id
            WHERE b.rule_set_id='01994d00-6c1a-7000-8000-00000000001c' AND p.decided_at < '2026-10-07 00:00Z')
SELECT r, count(*) FILTER (WHERE (blk->'refusals') ? 'mayhem_curve') may, count(*) FILTER (WHERE NOT (blk->'refusals') ? 'mayhem_curve') nonmay
FROM pb, jsonb_array_elements_text(blk->'refusals') r GROUP BY 1 ORDER BY 2+3 DESC;
WITH pb AS (SELECT p.reasons->0 blk FROM meme_paper_bets b JOIN meme_proposals p ON p.id=b.proposal_id
            WHERE b.rule_set_id='01994d00-6c1a-7000-8000-00000000001c' AND p.decided_at < '2026-10-07 00:00Z')
SELECT blk->>'refused_by' refused_by, count(*) FILTER (WHERE (blk->'refusals') ? 'mayhem_curve') may, count(*) FILTER (WHERE NOT (blk->'refusals') ? 'mayhem_curve') nonmay FROM pb GROUP BY 1 ORDER BY 2+3 DESC;
SELECT 'entry.snapshot' j, k, count(*) FROM meme_paper_bets b, jsonb_object_keys(CASE WHEN jsonb_typeof(b.entry->'snapshot')='object' THEN b.entry->'snapshot' ELSE '{}'::jsonb END) k WHERE b.rule_set_id='01994d00-6c1a-7000-8000-00000000001c' GROUP BY 1,2
UNION ALL SELECT 'exit.snapshot', k, count(*) FROM meme_paper_bets b, jsonb_object_keys(CASE WHEN jsonb_typeof(b.exit->'snapshot')='object' THEN b.exit->'snapshot' ELSE '{}'::jsonb END) k WHERE b.rule_set_id='01994d00-6c1a-7000-8000-00000000001c' GROUP BY 1,2 ORDER BY 1,2;
SELECT jsonb_typeof(entry->'snapshot') t, count(*) FROM meme_paper_bets WHERE rule_set_id='01994d00-6c1a-7000-8000-00000000001c' GROUP BY 1;
COMMIT;
