SET statement_timeout='120s';
BEGIN READ ONLY;
-- 11. só NOMES de chaves dos jsons da aposta da sonda (sem valores)
SELECT 'entry' j, k, count(*) FROM meme_paper_bets b, jsonb_object_keys(b.entry) k WHERE b.rule_set_id='01994d00-6c1a-7000-8000-00000000001c' GROUP BY 1,2
UNION ALL SELECT 'exit', k, count(*) FROM meme_paper_bets b, jsonb_object_keys(b.exit) k WHERE b.rule_set_id='01994d00-6c1a-7000-8000-00000000001c' GROUP BY 1,2
UNION ALL SELECT 'params', k, count(*) FROM meme_paper_bets b, jsonb_object_keys(b.params) k WHERE b.rule_set_id='01994d00-6c1a-7000-8000-00000000001c' GROUP BY 1,2 ORDER BY 1,2;
SELECT DISTINCT b.params::text FROM meme_paper_bets b WHERE b.rule_set_id='01994d00-6c1a-7000-8000-00000000001c' LIMIT 3;
SELECT leg, count(*) FROM meme_paper_bets WHERE rule_set_id='01994d00-6c1a-7000-8000-00000000001c' GROUP BY 1;
COMMIT;
