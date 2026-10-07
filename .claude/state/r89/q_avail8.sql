SET statement_timeout='120s';
BEGIN READ ONLY;
-- 13. auditoria "um sorteio por mint" (propostas da sonda, com ou sem aposta) — sem desfecho
SELECT count(*) props, count(DISTINCT mint) mints, count(*) FILTER (WHERE bet_id IS NULL) sem_aposta
FROM meme_proposals WHERE rule_set_id='01994d00-6c1a-7000-8000-00000000001c';
SELECT count(*) FROM (SELECT mint FROM meme_proposals WHERE rule_set_id='01994d00-6c1a-7000-8000-00000000001c' GROUP BY mint HAVING count(*)>1) x;
COMMIT;
