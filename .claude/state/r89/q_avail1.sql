SET statement_timeout='120s';
BEGIN READ ONLY;
SELECT current_setting('transaction_read_only') ro, now();
-- 1. propostas com bloco mayhem (sem desfechos)
SELECT x->>'is_mayhem' is_mayhem, x->>'excluded' excluded, count(*) n, count(DISTINCT p.mint) mints,
       min(p.decided_at) first_dec, max(p.decided_at) last_dec, count(DISTINCT date_trunc('day',p.features_end_time)) days
FROM meme_proposals p, jsonb_array_elements(p.reasons) x
WHERE x->>'feature'='mayhem' GROUP BY 1,2 ORDER BY 1,2;
-- 2. conjuntos que desligam o exclude_mayhem
SELECT name||'/'||version rs, status, params->>'exclude_mayhem' excl FROM meme_rule_sets WHERE params ? 'exclude_mayhem' ORDER BY 1;
COMMIT;
