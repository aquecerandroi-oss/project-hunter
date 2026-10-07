-- R88 passo 1 — disponibilidade CEGA (nenhuma coluna de desfecho: sem pnl, sem exit, sem preço de saída)
BEGIN READ ONLY;
SET LOCAL statement_timeout='300s';
\echo == schema meme_proposals / meme_paper_bets / meme_live_positions
SELECT table_name, string_agg(column_name||':'||data_type, ', ' ORDER BY ordinal_position)
FROM information_schema.columns
WHERE table_schema='public' AND table_name IN ('meme_proposals','meme_paper_bets','meme_live_positions','meme_rule_sets')
GROUP BY table_name;
\echo == conjuntos com pedigree_e2b ligado
SELECT name||'/'||version AS rs, kind, status, params->>'pedigree_e2b' AS e2b, created_at
FROM meme_rule_sets WHERE (params->>'pedigree_e2b')::boolean IS TRUE ORDER BY created_at;
COMMIT;
