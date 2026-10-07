-- R91 passo 1b — disponibilidade CEGA: histórico de parâmetros e o bloco flow por conjunto (só covariáveis da decisão)
BEGIN READ ONLY;
SET LOCAL statement_timeout='600s';
\echo == colunas do histórico de parâmetros
SELECT column_name FROM information_schema.columns WHERE table_name='meme_rule_set_param_history' ORDER BY ordinal_position;
\echo == propostas por conjunto: com bloco flow e distribuição de holders_rising / progress_rising (true/false/nulo)
WITH f AS (
  SELECT p.id, p.mint, p.proposed_at, rs.name||'/'||rs.version rs, p.reasons->0->>'series' series, e AS fl
  FROM meme_proposals p JOIN meme_rule_sets rs ON rs.id=p.rule_set_id
  LEFT JOIN LATERAL (SELECT e FROM jsonb_array_elements(p.reasons) e WHERE e->>'feature'='flow' LIMIT 1) x ON true
  WHERE jsonb_typeof(p.reasons)='array')
SELECT rs, series, count(*) props, count(fl) com_flow, count(DISTINCT mint) mints,
       count(DISTINCT (proposed_at AT TIME ZONE 'UTC')::date) dias, min(proposed_at)::date primeiro, max(proposed_at)::date ultimo,
       count(*) FILTER (WHERE fl->>'holders_rising'='true') h_t, count(*) FILTER (WHERE fl->>'holders_rising'='false') h_f,
       count(*) FILTER (WHERE fl IS NOT NULL AND fl->>'holders_rising' IS NULL) h_nulo,
       count(*) FILTER (WHERE fl->>'progress_rising'='true') p_t, count(*) FILTER (WHERE fl->>'progress_rising'='false') p_f,
       count(*) FILTER (WHERE fl IS NOT NULL AND fl->>'progress_rising' IS NULL) p_nulo
FROM f GROUP BY 1,2 ORDER BY 1,2;
COMMIT;
